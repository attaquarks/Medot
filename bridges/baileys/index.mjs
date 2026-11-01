/**
 * Medot Baileys bridge (Route 2 — unofficial WhatsApp Web session).
 *
 * Emulates a WhatsApp Web session via @whiskeysockets/baileys and exposes a
 * tiny loopback HTTP API to the Medot runtime (Python sidecar):
 *
 *   GET  /health                     -> { connected, paired, user }
 *   GET  /qr                         -> { qr: <data-url>|null, paired }  (current pairing QR)
 *   GET  /updates?cursor=N&timeout=S -> { updates: [...], cursor }       (long poll, same shape
 *                                                                         as the Agent Platform path)
 *   POST /send   {to, text}          -> { id }                            (bare number or JID)
 *   POST /logout                     -> { ok }                            (unpair + wipe session)
 *
 * All endpoints require `Authorization: Bearer <token>` (the runtime passes a
 * per-launch token); the server binds 127.0.0.1 only. The WhatsApp session is
 * persisted under --session and grants full account access — protect it like
 * a password, never commit it.
 *
 * Inbound policy (mirrors the Hermes WhatsApp bridge):
 *   mode self  — the user messages themselves; only their own chat is read
 *                (messages typed on the phone; the bridge's own sends are
 *                suppressed by id).
 *   mode bot   — a dedicated number; DMs from allowlisted senders, groups per
 *                --group-policy (pairing | allowlist | open) and
 *                --require-mention. No allowlist => deny all inbound.
 *
 * UNOFFICIAL: small ban risk. Use a dedicated number for bot mode.
 */
import http from "node:http";
import crypto from "node:crypto";
import path from "node:path";
import fs from "node:fs";
import { setTimeout as delay } from "node:timers/promises";
import pino from "pino";
import QRCode from "qrcode";
import makeWASocket, {
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
} from "@whiskeysockets/baileys";
import { Boom } from "@hapi/boom";

const log = pino({ level: process.env.BRIDGE_LOG_LEVEL || "warn" });

// ---------------------------------------------------------------- CLI args
function parseArgs(argv) {
  const out = {
    port: 0, // 0 = ask the OS for a free port (printed on stdout)
    token: "",
    session: path.join(process.cwd(), "session"),
    mode: "bot", // "bot" | "self"
    allow: [], // phone numbers (country code, no +) or ["*"]
    groupPolicy: "pairing", // "pairing" | "allowlist" | "open"
    groupAllow: [], // group JIDs like 120363...@g.us
    requireMention: false,
  };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    const next = () => argv[++i];
    if (a === "--port") out.port = Number(next());
    else if (a === "--token") out.token = String(next());
    else if (a === "--session") out.session = path.resolve(String(next()));
    else if (a === "--mode") out.mode = String(next());
    else if (a === "--allow") out.allow = String(next()).split(",").map((s) => s.trim()).filter(Boolean);
    else if (a === "--group-policy") out.groupPolicy = String(next());
    else if (a === "--group-allow") out.groupAllow = String(next()).split(",").map((s) => s.trim()).filter(Boolean);
    else if (a === "--require-mention") out.requireMention = true;
  }
  return out;
}

const cfg = parseArgs(process.argv);
cfg.allowAll = cfg.allow.includes("*");
cfg.allowDigits = new Set(cfg.allow.filter((a) => a !== "*").map((a) => a.replace(/\D/g, "")));

// ---------------------------------------------------------------- state
let sock = null;
let connected = false;
let paired = false;
let currentQR = null; // data URL
let ownJid = ""; // e.g. 15551234567:12@s.whatsapp.net
let ownDigits = "";
let restarting = false;

// Inbound long-poll machinery (uniform with GET /updates on the Agent Platform)
let seq = 0;
const pending = []; // { seq, update }
const waiters = new Set(); // { resolve, timer }
const seenIds = new Set(); // inbound dedupe ring
const SENT_RING_MAX = 1000;
const sentIds = new Set(); // our own sends (self-chat echo suppression)
const sentOrder = [];

function rememberSent(id) {
  sentIds.add(id);
  sentOrder.push(id);
  while (sentOrder.length > SENT_RING_MAX) sentIds.delete(sentOrder.shift());
}

function rememberSeen(id) {
  if (seenIds.has(id)) return false;
  seenIds.add(id);
  if (seenIds.size > SENT_RING_MAX) {
    const first = seenIds.values().next().value;
    seenIds.delete(first);
  }
  return true;
}

function digitsOf(jid) {
  if (!jid) return "";
  return String(jid).split("@")[0].split(":")[0].replace(/\D/g, "");
}

function pushUpdate(update) {
  update.seq = ++seq;
  pending.push(update);
  while (pending.length > 1000) pending.shift();
  for (const w of waiters) {
    clearTimeout(w.timer);
    w.resolve();
  }
  waiters.clear();
}

// ------------------------------------------------------------- WhatsApp
async function normalizeMessage(m) {
  if (!m?.key || !m.message) return null;
  const chat = m.key.remoteJid || "";
  if (!chat || chat === "status@broadcast" || chat.endsWith("@newsletter")) return null;

  const isGroup = chat.endsWith("@g.us");
  const fromMe = !!m.key.fromMe;
  const keyId = m.key.id || "";
  if (!keyId) return null;

  // Sender resolution: prefer the phone number Baileys supplies (LID fallback).
  const senderJid = m.senderPn || m.key.participant || chat;
  const senderDigits = digitsOf(senderJid) || digitsOf(chat);

  // ---- mode + policy gates --------------------------------------------
  if (cfg.mode === "self") {
    // Self-chat: only the user's own chat, typed on the phone (fromMe),
    // excluding the bridge's own echoes.
    if (!fromMe) return null;
    if (digitsOf(chat) !== ownDigits) return null;
    if (sentIds.has(keyId)) return null;
  } else {
    if (fromMe) return null;
    const senderAllowed = cfg.allowAll || cfg.allowDigits.has(senderDigits);
    if (isGroup) {
      if (cfg.groupPolicy === "pairing") return null;
      if (cfg.groupPolicy === "allowlist") {
        const groupOk = cfg.groupAllow.includes(chat);
        const senderOk = cfg.allow.length > 0 ? senderAllowed : groupOk;
        if (!groupOk || !senderOk) return null;
      } else if (cfg.groupPolicy === "open") {
        if (!senderAllowed) return null;
      }
      if (cfg.requireMention && !isMentioned(m)) return null;
    } else if (!senderAllowed) {
      return null;
    }
  }

  if (!rememberSeen(`${chat}:${keyId}`)) return null;

  // ---- payload ---------------------------------------------------------
  const msg = m.message;
  const text =
    msg.conversation ||
    msg.extendedTextMessage?.text ||
    msg.imageMessage?.caption ||
    msg.videoMessage?.caption ||
    msg.documentMessage?.caption ||
    "";
  let media = null;
  for (const [kind, key] of [
    ["image", "imageMessage"],
    ["video", "videoMessage"],
    ["audio", "audioMessage"],
    ["document", "documentMessage"],
    ["sticker", "stickerMessage"],
  ]) {
    if (msg[key]) {
      media = {
        kind,
        mime: msg[key].mimetype || null,
        filename: msg[key].fileName || null,
      };
      break;
    }
  }
  if (!text && !media) return null; // unsupported/empty

  const ts = Number(m.messageTimestamp) || Math.floor(Date.now() / 1000);
  return {
    id: `${chat}:${keyId}`,
    transport: "baileys",
    chat,
    peer: cfg.mode === "self" ? ownJid : chat,
    sender: senderDigits || senderJid,
    sender_name: m.pushName || null,
    text,
    media,
    timestamp: ts,
  };
}

function isMentioned(m) {
  const ctx = m.message?.extendedTextMessage?.contextInfo;
  const mentioned = ctx?.mentionedJid || [];
  if (mentioned.some((j) => digitsOf(j) === ownDigits)) return true;
  if (ctx?.participant && digitsOf(ctx.participant) === ownDigits) return true; // reply to the bot
  const text = m.message?.conversation || m.message?.extendedTextMessage?.text || "";
  return text.startsWith("/");
}

async function startSocket() {
  const { state, saveCreds } = await useMultiFileAuthState(cfg.session);
  let version;
  try {
    ({ version } = await fetchLatestBaileysVersion());
  } catch {
    version = undefined; // offline: Baileys ships a default
  }
  sock = makeWASocket({ version, auth: state, logger: log.child({ module: "baileys" }) });

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", async (update) => {
    const { connection, lastDisconnect, qr } = update;
    if (qr) {
      try {
        currentQR = await QRCode.toDataURL(qr);
      } catch {
        currentQR = null;
      }
      log.info("qr_updated");
    }
    if (connection === "open") {
      connected = true;
      paired = true;
      currentQR = null;
      ownJid = sock.user?.id || "";
      ownDigits = digitsOf(ownJid);
      console.log(JSON.stringify({ event: "bridge_ready", paired: true, user: ownDigits }));
    }
    if (connection === "close") {
      connected = false;
      const code = (lastDisconnect?.error instanceof Boom)
        ? lastDisconnect.error.output.statusCode
        : lastDisconnect?.error?.output?.statusCode;
      const loggedOut = code === DisconnectReason.loggedOut;
      log.warn({ code, loggedOut }, "whatsapp_disconnected");
      if (loggedOut) {
        paired = false;
        currentQR = null;
        try {
          fs.rmSync(cfg.session, { recursive: true, force: true });
        } catch { /* best effort */ }
        console.log(JSON.stringify({ event: "bridge_logged_out" }));
        return; // wait for an explicit re-pair via restart
      }
      if (!restarting) startSocket().catch((e) => log.error({ err: String(e) }, "restart_failed"));
    }
  });

  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") return;
    for (const m of messages) {
      try {
        const update = await normalizeMessage(m);
        if (update) pushUpdate(update);
      } catch (err) {
        log.error({ err: String(err) }, "normalize_failed");
      }
    }
  });
}

function toJid(to) {
  const raw = String(to || "").trim();
  if (raw.includes("@")) return raw;
  const digits = raw.replace(/\D/g, "");
  if (!digits) throw new Error("send: a destination is required");
  if (cfg.mode === "self" && (digits === ownDigits || digits === "me")) return ownJid;
  return `${digits}@s.whatsapp.net`;
}

// ---------------------------------------------------------------- HTTP API
function authorized(req) {
  const header = req.headers["authorization"] || "";
  const expected = `Bearer ${cfg.token}`;
  if (header.length !== expected.length) return false;
  return crypto.timingSafeEqual(Buffer.from(header), Buffer.from(expected));
}

function sendJson(res, status, body) {
  const data = JSON.stringify(body);
  res.writeHead(status, { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(data) });
  res.end(data);
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let data = "";
    req.on("data", (c) => {
      data += c;
      if (data.length > 1_000_000) reject(new Error("body too large"));
    });
    req.on("end", () => {
      try {
        resolve(data ? JSON.parse(data) : {});
      } catch (e) {
        reject(e);
      }
    });
    req.on("error", reject);
  });
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, "http://127.0.0.1");
  if (!authorized(req)) return sendJson(res, 401, { error: "unauthorized" });

  try {
    if (req.method === "GET" && url.pathname === "/health") {
      return sendJson(res, 200, { connected, paired, user: ownDigits, mode: cfg.mode });
    }

    if (req.method === "GET" && url.pathname === "/qr") {
      return sendJson(res, 200, { qr: paired ? null : currentQR, paired });
    }

    if (req.method === "GET" && url.pathname === "/updates") {
      const cursor = Number(url.searchParams.get("cursor") || 0);
      const timeoutS = Math.min(25, Math.max(0, Number(url.searchParams.get("timeout") || 20)));
      const ready = pending.length > 0 && pending[0].seq > cursor;
      if (!ready && timeoutS > 0) {
        await new Promise((resolve) => {
          const w = { resolve, timer: null };
          w.timer = setTimeout(() => {
            waiters.delete(w);
            resolve();
          }, timeoutS * 1000);
          waiters.add(w);
        });
      }
      const updates = pending.filter((u) => u.seq > cursor);
      return sendJson(res, 200, {
        updates,
        cursor: pending.length ? pending[pending.length - 1].seq : seq,
      });
    }

    if (req.method === "POST" && url.pathname === "/send") {
      const { to, text } = await readBody(req);
      if (!sock || !connected) return sendJson(res, 503, { error: "not connected" });
      const jid = toJid(to);
      const info = await sock.sendMessage(jid, { text: String(text ?? "") });
      if (info?.key?.id) rememberSent(info.key.id);
      return sendJson(res, 200, { id: `${jid}:${info?.key?.id || ""}` });
    }

    if (req.method === "POST" && url.pathname === "/typing") {
      const { to } = await readBody(req);
      if (sock && connected) await sock.sendPresenceUpdate("composing", toJid(to));
      return sendJson(res, 200, { ok: true });
    }

    if (req.method === "POST" && url.pathname === "/logout") {
      try {
        await sock?.logout();
      } catch { /* already gone */ }
      connected = false;
      paired = false;
      currentQR = null;
      try {
        fs.rmSync(cfg.session, { recursive: true, force: true });
      } catch { /* best effort */ }
      restarting = true; // do not auto-reconnect over a wiped session
      return sendJson(res, 200, { ok: true });
    }

    return sendJson(res, 404, { error: "not found" });
  } catch (err) {
    log.error({ err: String(err) }, "request_failed");
    return sendJson(res, 500, { error: "internal" });
  }
});

server.listen(cfg.port, "127.0.0.1", () => {
  const { port } = server.address();
  // Handshake line for the runtime: it discovers the actual bound port here.
  console.log(JSON.stringify({ event: "bridge_listening", port, pid: process.pid }));
});

async function main() {
  await startSocket();
  // Keep the process alive even if the socket is between reconnects.
  for (;;) await delay(60_000);
}

main().catch((e) => {
  console.log(JSON.stringify({ event: "bridge_failed", error: String(e) }));
  process.exit(1);
});

process.on("SIGTERM", () => process.exit(0));
process.on("SIGINT", () => process.exit(0));
