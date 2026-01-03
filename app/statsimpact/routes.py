from __future__ import annotations

from datetime import date

from flask import Blueprint, abort, render_template, request
from flask_login import login_required, current_user

from app.models import AtelierActivite

from .occupancy import compute_occupancy_stats

from .engine import (
    compute_volume_activity_stats,
    compute_participation_frequency_stats,
    compute_transversalite_stats,
    compute_demography_stats,
    normalize_filters,
)

bp = Blueprint("statsimpact", __name__, url_prefix="")


def _can_view() -> bool:
    return getattr(current_user, "role", None) in (
        "finance",
        "financiere",
        "financière",
        "directrice",
        "responsable_secteur",
        "admin_tech",
    )


@bp.route("/stats-impact")
@login_required
def dashboard():
    if not _can_view():
        abort(403)

    args = dict(request.args)

    # Robust: normalize_filters supports both dict-style and kwargs-style.
    flt = normalize_filters(args, user=current_user)

    # Default: current year if no dates
    if not flt.date_from and not flt.date_to:
        today = date.today()
        flt.date_from = date(today.year, 1, 1)
        flt.date_to = date(today.year, 12, 31)

    stats = compute_volume_activity_stats(flt)
    freq = compute_participation_frequency_stats(flt)
    trans = compute_transversalite_stats(flt)
    demo = compute_demography_stats(flt)
    occupancy = compute_occupancy_stats(flt)

    secteurs = []
    if getattr(current_user, "role", None) in ("finance", "financiere", "financière", "directrice", "admin_tech"):
        secteurs = [
            s[0]
            for s in (
                AtelierActivite.query.with_entities(AtelierActivite.secteur)
                .filter(AtelierActivite.is_deleted.is_(False))
                .distinct()
                .order_by(AtelierActivite.secteur.asc())
                .all()
            )
            if s and s[0]
        ]

    q = AtelierActivite.query.filter(AtelierActivite.is_deleted.is_(False))
    if flt.secteur:
        q = q.filter(AtelierActivite.secteur == flt.secteur)
    ateliers = q.order_by(AtelierActivite.secteur.asc(), AtelierActivite.nom.asc()).all()

    return render_template(
        ["statsimpact/dashboard.html", "statsimpact_dashboard.html"],
        flt=flt,
        stats=stats,
        freq=freq,
        trans=trans,
        demo=demo,
        secteurs=secteurs,
        ateliers=ateliers,
        occupancy=occupancy,
    )
