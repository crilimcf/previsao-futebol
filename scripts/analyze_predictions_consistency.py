import json
from pathlib import Path


def load_preds(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def pct(x):
    return round(float(x) * 100.0, 2)


def main():
    p = Path(__file__).resolve().parents[1] / "data" / "predict" / "predictions.json"
    preds = load_preds(p)

    issues = {
        "probable_empty": [],
        "probable_team_mismatch": [],
        "explanation_mismatch": [],
        "odds_caps": [],
    }

    for m in preds:
        mid = m.get("match_id")
        home = m.get("home_team")
        away = m.get("away_team")

        # probable scorers empty but top_scorers non-empty
        ph = m.get("probable_scorers_home") or []
        pa = m.get("probable_scorers_away") or []
        ts = m.get("top_scorers") or []
        if (not ph) and ts:
            issues["probable_empty"].append((mid, home, away, len(ts)))
        if (not pa) and ts:
            issues["probable_empty"].append((mid, home, away, len(ts)))

        # team mismatch: probable scorer team_name doesn't match fixture team
        for p_obj in ph:
            if p_obj.get("team_name") and p_obj.get("team_name") != home:
                issues["probable_team_mismatch"].append((mid, "home", home, p_obj.get("team_name"), p_obj.get("name")))
        for p_obj in pa:
            if p_obj.get("team_name") and p_obj.get("team_name") != away:
                issues["probable_team_mismatch"].append((mid, "away", away, p_obj.get("team_name"), p_obj.get("name")))

        # explanation vs v2 numbers (btts, over25)
        expl = " ".join(m.get("explanation") or [])
        v2 = m.get("v2") or {}
        try:
            btts_final = None
            if v2.get("btts") and v2["btts"].get("final"):
                btts_final = v2["btts"]["final"].get("yes")
            ou_final = None
            if v2.get("ou25") and v2["ou25"].get("final"):
                ou_final = v2["ou25"]["final"].get("over")

            # parse explanation numbers if present
            if "BTTS" in expl and btts_final is not None:
                # find occurrences like 'BTTS Não 96%' or 'BTTS Sim 46%'
                import re

                m_bt = re.search(r"BTTS\s+(Sim|Não)\s*(\d{1,3})%", expl)
                if m_bt:
                    kind = m_bt.group(1)
                    val = int(m_bt.group(2)) / 100.0
                    if kind == "Sim":
                        expected = btts_final
                    else:
                        expected = 1.0 - btts_final
                    if abs(expected - val) > 0.05:
                        issues["explanation_mismatch"].append((mid, "btts", val, round(expected, 3), expl))

            if "Over 2.5" in expl and ou_final is not None:
                import re
                m_ou = re.search(r"Over 2\.5 golos \((\d{1,3})%\)", expl)
                if m_ou:
                    val = int(m_ou.group(1)) / 100.0
                    if abs(ou_final - val) > 0.05:
                        issues["explanation_mismatch"].append((mid, "over25", val, round(ou_final, 3), expl))
        except Exception:
            pass

        # odds caps: detect many odds equal to 50.0 or 1.2 which suggest capping
        odds = m.get("odds") or {}
        for market, vals in odds.items():
            for k, v in (vals or {}).items():
                try:
                    fv = float(v)
                    if fv == 50.0 or fv == 1.2:
                        issues["odds_caps"].append((mid, market, k, fv))
                except Exception:
                    continue

    # print summary
    print("Issues summary:")
    for k, v in issues.items():
        print(f" - {k}: {len(v)}")

    # Save details for inspection
    out = Path("tmp") / "predictions_consistency_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(issues, f, ensure_ascii=False, indent=2)

    print(f"Detailed report written to {out}")


if __name__ == "__main__":
    main()
