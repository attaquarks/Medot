/**
 * AIA WhatsApp sidecar (Baileys).
 *
 * Owns the WhatsApp Web socket and exposes a tiny REST API the Python core uses:
 *   GET  /health           -> { connected }
 *   GET  /qr               -> { qr }  (data-URL PNG, present until paired)
 *   POST /send  {to,text}  -> sends a text message
 *   POST /typing {to}      -> sends a "typing…" presence
 *
 * Inbound messages are forwarded to the Python gateway:
 *   POST {GATEWAY_INBOUND_URL}  { from, text }
 *
 * Auth/session is persisted to ./auth_info (a docker volume) so pairing survives
 * restarts. To switch to Meta's official Cloud API, set WHATSAPP_PROVIDER=cloud
 * in the Python core — this sidecar is only used for the Baileys path.
 */
import express from "express";
import axios from "axios";
import qrcode from "qrcode";
import pino from "pino";
import makeWASocket, {
  useMultiFileAuthState,
  DisconnectReason,
  type WASocket,
} from "@whiskeysockets/baileys";
import { Boom } from "@hapi/boom";

const log = pino({ level: process.env.LOG_LEVEL || "info" });
const PORT = Number(process.env.WA_GATEWAY_PORT || 8085);
const GATEWAY_INBOUND_URL =
  process.env.GATEWAY_INBOUND_URL || "http://gateway:8080/webhook/whatsapp";
const NUMBER_TAG = process.env.WA_NUMBER_TAG || ""; // "business" | "health" | ""

let sock: WASocket | null = null;
let currentQR: string | null = null;
let connected = false;

async function start() {
  const { state, saveCreds } = await useMultiFileAuthState("auth_info");
  sock = makeWASocket({ auth: state, printQRInTerminal: false, logger: log });

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", async (update) => {
    const { connection, lastDisconnect, qr } = update;
    if (qr) {
      currentQR = await qrcode.toDataURL(qr);
      log.info("qr_updated — open the onboarding page to scan");
    }
    if (connection === "open") {
      connected = true;
      currentQR = null;
      log.info("whatsapp_connected");
    }
    if (connection === "close") {
      connected = false;
      const code = (lastDisconnect?.error as Boom)?.output?.statusCode;
      const shouldReconnect = code !== DisconnectReason.loggedOut;
      log.warn({ code, shouldReconnect }, "whatsapp_disconnected");
      if (shouldReconnect) start();
    }
  });

  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") return;
    for (const m of messages) {
      if (m.key.fromMe || !m.message) continue;
      const from = m.key.remoteJid || "";
      // Only 1:1 chats: ignore groups, status broadcasts and newsletters.
      if (
        from.endsWith("@g.us") ||
        from === "status@broadcast" ||
        from.endsWith("@newsletter")
      ) {
        continue;
      }
      const text =
        m.message.conversation ||
        m.message.extendedTextMessage?.text ||
        "";
      if (!text) continue;
      try {
        await axios.post(GATEWAY_INBOUND_URL, {
          from,
          text,
          number_tag: NUMBER_TAG || undefined,
        });
      } catch (err) {
        log.error({ err: String(err) }, "forward_failed");
      }
    }
  });
}

const app = express();
app.use(express.json());

app.get("/health", (_req, res) => res.json({ connected }));
app.get("/qr", (_req, res) => res.json({ qr: currentQR }));

app.post("/send", async (req, res) => {
  const { to, text } = req.body ?? {};
  if (!sock || !connected) return res.status(503).json({ error: "not connected" });
  try {
    await sock.sendMessage(to, { text });
    res.json({ status: "sent" });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

app.post("/typing", async (req, res) => {
  const { to } = req.body ?? {};
  try {
    await sock?.sendPresenceUpdate("composing", to);
    res.json({ status: "ok" });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

app.listen(PORT, () => log.info(`wa-gateway listening on :${PORT}`));
start().catch((e) => log.error({ err: String(e) }, "startup_failed"));
