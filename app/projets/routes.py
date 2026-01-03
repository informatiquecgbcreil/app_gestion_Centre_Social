import os
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, current_app, send_from_directory
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import Projet, Subvention, SubventionProjet

bp = Blueprint("projets", __name__)

ALLOWED_CR = {"pdf", "doc", "docx", "odt"}

def can_see_secteur(secteur: str) -> bool:
    if current_user.role in ("directrice", "finance"):
        return True
    if current_user.role == "responsable_secteur":
        return current_user.secteur_assigne == secteur
    return False

def ensure_projets_folder():
    folder = os.path.join(current_app.root_path, "..", "static", "uploads", "projets")
    folder = os.path.abspath(folder)
    os.makedirs(folder, exist_ok=True)
    return folder

def allowed_cr(filename: str) -> bool:
    if not filename or "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_CR

@bp.route("/projets")
@login_required
def projets_list():
    if current_user.role == "admin_tech":
        abort(403)

    q = Projet.query
    if current_user.role == "responsable_secteur":
        q = q.filter(Projet.secteur == current_user.secteur_assigne)

    projets = q.order_by(Projet.created_at.desc()).all()
    secteurs = current_app.config.get("SECTEURS", [])
    return render_template("projets_list.html", projets=projets, secteurs=secteurs)

@bp.route("/projets/new", methods=["GET", "POST"])
@login_required
def projets_new():
    if current_user.role == "admin_tech":
        abort(403)

    secteurs = current_app.config.get("SECTEURS", [])

    if request.method == "POST":
        nom = (request.form.get("nom") or "").strip()
        secteur = (request.form.get("secteur") or "").strip()
        description = (request.form.get("description") or "").strip()

        if current_user.role == "responsable_secteur":
            secteur = current_user.secteur_assigne

        if not nom or not secteur:
            flash("Nom + secteur obligatoires.", "danger")
            return redirect(url_for("projets.projets_new"))

        if not can_see_secteur(secteur):
            abort(403)

        p = Projet(nom=nom, secteur=secteur, description=description)
        db.session.add(p)
        db.session.commit()

        flash("Projet créé.", "success")
        return redirect(url_for("projets.projets_edit", projet_id=p.id))

    return render_template("projets_new.html", secteurs=secteurs)

@bp.route("/projets/<int:projet_id>", methods=["GET", "POST"])
@login_required
def projets_edit(projet_id):
    if current_user.role == "admin_tech":
        abort(403)

    p = Projet.query.get_or_404(projet_id)
    if not can_see_secteur(p.secteur):
        abort(403)

    if request.method == "POST":
        action = request.form.get("action") or ""

        if action == "update":
            p.nom = (request.form.get("nom") or "").strip()
            p.description = (request.form.get("description") or "").strip()

            if not p.nom:
                flash("Nom obligatoire.", "danger")
                return redirect(url_for("projets.projets_edit", projet_id=p.id))

            db.session.commit()
            flash("Projet modifié.", "success")
            return redirect(url_for("projets.projets_edit", projet_id=p.id))

        if action == "upload_cr":
            file = request.files.get("cr_file")
            if not file or not file.filename:
                flash("Aucun fichier.", "danger")
                return redirect(url_for("projets.projets_edit", projet_id=p.id))

            if not allowed_cr(file.filename):
                flash("Type autorisé : pdf/doc/docx/odt", "danger")
                return redirect(url_for("projets.projets_edit", projet_id=p.id))

            folder = ensure_projets_folder()
            safe_original = secure_filename(file.filename)
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            stored = secure_filename(f"P{p.id}_{ts}_{safe_original}")
            file.save(os.path.join(folder, stored))

            p.cr_filename = stored
            p.cr_original_name = safe_original
            db.session.commit()

            flash("Compte-rendu uploadé.", "success")
            return redirect(url_for("projets.projets_edit", projet_id=p.id))

        if action == "toggle_subvention":
            sub_id = int(request.form.get("subvention_id") or 0)
            s = Subvention.query.get_or_404(sub_id)

            if s.secteur != p.secteur:
                abort(400)

            link = SubventionProjet.query.filter_by(projet_id=p.id, subvention_id=s.id).first()
            if link:
                db.session.delete(link)
                db.session.commit()
                flash("Subvention retirée du projet.", "warning")
            else:
                db.session.add(SubventionProjet(projet_id=p.id, subvention_id=s.id))
                db.session.commit()
                flash("Subvention ajoutée au projet.", "success")

            return redirect(url_for("projets.projets_edit", projet_id=p.id))

        abort(400)

    subs_q = Subvention.query.filter_by(est_archive=False).filter(Subvention.secteur == p.secteur)
    subs = subs_q.order_by(Subvention.annee_exercice.desc(), Subvention.nom.asc()).all()
    linked = set(sp.subvention_id for sp in p.subventions)

    return render_template("projets_edit.html", projet=p, subs=subs, linked=linked)

@bp.route("/projets/cr/<int:projet_id>/download")
@login_required
def projets_cr_download(projet_id):
    if current_user.role == "admin_tech":
        abort(403)

    p = Projet.query.get_or_404(projet_id)
    if not can_see_secteur(p.secteur):
        abort(403)

    if not p.cr_filename:
        abort(404)

    folder = ensure_projets_folder()
    return send_from_directory(folder, p.cr_filename, as_attachment=True, download_name=(p.cr_original_name or p.cr_filename))
