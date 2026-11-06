"""An editable planning model, not measured insurer performance."""
import json


def compare(monthly_claims=1000, review_share=0.30):
    if monthly_claims <= 0 or not 0 <= review_share <= 1:
        raise ValueError("Positive volume and a review share between zero and one required")
    wage, build_rate, hours_per_worker = 45, 60, 160
    choices = [
        ("Manual checklist", 0, 0, 0, 12),
        ("Shared spreadsheet", 40, 2, 10, 8),
        ("Rules-assisted intake", 120, 4, 25, 3 * (1 - review_share) + 12 * review_share),
    ]
    rows = []
    for name, build_hours, maintenance, monthly_hosting, minutes in choices:
        monthly_hours = monthly_claims * minutes / 60
        ongoing = monthly_hours * wage + maintenance * build_rate + monthly_hosting
        rows.append({"option": name, "minutes_per_claim": round(minutes, 2),
                     "monthly_handling_hours": round(monthly_hours, 2),
                     "claims_per_160h": round(hours_per_worker * 60 / minutes),
                     "setup_cad": build_hours * build_rate,
                     "annual_running_cad": round(ongoing * 12, 2),
                     "first_year_cad": round(build_hours * build_rate + ongoing * 12, 2)})
    return {"fictional_planning_assumptions": {"monthly_claims": monthly_claims,
             "review_share": review_share, "handling_cad_per_hour": wage,
             "build_maintenance_cad_per_hour": build_rate, "hours_per_worker_month": hours_per_worker},
            "options": rows}


if __name__ == "__main__":
    print(json.dumps({"base": compare(), "60_percent_review": compare(review_share=0.6),
                      "all_review": compare(review_share=1)}, indent=2))
