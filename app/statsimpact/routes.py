from __future__ import annotations

from datetime import date

from flask import Blueprint, abort, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from app.models import AtelierActivite, Participant, Quartier

from .occupancy import compute_occupancy_stats

from .engine import (
    compute_volume_activity_stats,
    compute_participation_frequency_stats,
    compute_transversalite_stats,
    compute_demography_stats,
    compute_participants_stats,
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


@bp.route("/stats-impact", methods=["GET", "POST"])
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

    # Pre-compute participants for access control if we need to handle edits.
    participants = compute_participants_stats(flt)

    if request.method == "POST":
        action = request.form.get("action")
        if action == "update_participant":
            try:
                participant_id = int(request.form.get("participant_id", "0"))
            except Exception:
                participant_id = 0

            allowed_ids = {p["id"] for p in participants.get("participants", [])}
            if not participant_id or participant_id not in allowed_ids:
                abort(403)

            participant = Participant.query.get(participant_id)
            if not participant:
                abort(404)

            participant.nom = (request.form.get("nom") or participant.nom or "").strip() or participant.nom
            participant.prenom = (request.form.get("prenom") or participant.prenom or "").strip() or participant.prenom
            participant.ville = (request.form.get("ville") or "").strip() or None
            participant.email = (request.form.get("email") or "").strip() or None
            participant.telephone = (request.form.get("telephone") or "").strip() or None
            participant.genre = (request.form.get("genre") or "").strip() or None
            participant.type_public = (request.form.get("type_public") or participant.type_public or "H").strip().upper()

            dn_raw = request.form.get("date_naissance") or None
            dn = None
            if dn_raw:
                try:
                    dn = date.fromisoformat(dn_raw)
                except Exception:
                    dn = None
            participant.date_naissance = dn

            quartier_id = request.form.get("quartier_id") or None
            try:
                participant.quartier_id = int(quartier_id) if quartier_id else None
            except Exception:
                participant.quartier_id = None

            try:
                from app.extensions import db

                db.session.commit()
                flash("Participant mis à jour.", "success")
            except Exception:
                db.session.rollback()
                flash("Impossible de sauvegarder ce participant.", "danger")

            args_redirect = request.args.to_dict(flat=True)
            args_redirect["tab"] = "participants"
            return redirect(url_for("statsimpact.dashboard", **args_redirect))

    # Refresh computed stats after any potential mutation
    participants = compute_participants_stats(flt)
    stats = compute_volume_activity_stats(flt)
    freq = compute_participation_frequency_stats(flt)
    trans = compute_transversalite_stats(flt)
    demo = compute_demography_stats(flt)
    occupancy = compute_occupancy_stats(flt)
    participants = compute_participants_stats(flt)

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

    quartiers = Quartier.query.order_by(Quartier.nom.asc()).all()

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
        participants=participants,
        quartiers=quartiers,
    )
