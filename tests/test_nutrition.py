"""Unit tests for the energy-balance math (pure functions, no I/O)."""
from aia.agents.health import nutrition as nut


def test_bmr_mifflin_male():
    # 80kg, 180cm, 30y male -> 10*80 + 6.25*180 - 5*30 + 5 = 1780
    assert round(nut.bmr_mifflin("male", 80, 180, 30)) == 1780


def test_bmr_mifflin_female():
    # 65kg, 165cm, 30y female -> 10*65 + 6.25*165 - 5*30 - 161 = 1370.25
    assert round(nut.bmr_mifflin("female", 65, 165, 30), 2) == 1370.25


def test_tdee_activity_factor():
    assert nut.tdee(1780, "moderate") == 1780 * 1.55
    assert nut.tdee(1780, "sedentary") == 1780 * 1.2


def test_calorie_target_deficit():
    tdee = 2500
    # 0.5 kg/week loss = 3850 kcal/wk = 550 kcal/day deficit -> 1950
    assert nut.calorie_target(tdee, "lose", 0.5) == 1950


def test_calorie_target_floor():
    # Aggressive deficit must never go below the 1200 floor.
    assert nut.calorie_target(1500, "lose", 1.0) == 1200


def test_calorie_target_maintain_and_gain():
    assert nut.calorie_target(2200, "maintain") == 2200
    assert nut.calorie_target(2200, "gain", 0.5) == 2200 + 550


def test_calories_burned_running():
    # 9.8 MET * 70kg * 0.5h = 343 kcal
    assert round(nut.calories_burned("running", 70, 30)) == 343


def test_projected_weeks_to_goal():
    # lose 5kg at 550 kcal/day deficit -> ~3850/wk -> 0.5kg/wk -> 10 weeks
    assert nut.projected_weeks_to_goal(80, 75, 550) == 10.0


def test_day_progress():
    p = nut.DayProgress(target=2000, consumed=1800, burned=300)
    assert p.remaining == 500          # 2000 - 1800 + 300
    assert p.on_track is True
    over = nut.DayProgress(target=2000, consumed=2600, burned=0)
    assert over.on_track is False
