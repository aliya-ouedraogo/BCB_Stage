from django.core.management.base import BaseCommand

from appStage.models import ProfilMaitreStage, ProfilRH, ProfilStagiaire, User


class Command(BaseCommand):
    help = (
        "Nettoie les profils (Stagiaire / Maître de stage / RH) orphelins : ceux dont "
        "le compte User associé a été supprimé en base sans passer par Django (ex. "
        "suppression directe via un outil MySQL), ce qui empêche la suppression en "
        "cascade normalement prévue dans le code et laisse une ligne bloquée derrière."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help="N'affiche que ce qui serait supprimé, sans rien supprimer réellement.",
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        ids_utilisateurs_existants = set(User.objects.values_list('id', flat=True))

        total = 0
        for modele, label in [
            (ProfilStagiaire, "ProfilStagiaire"),
            (ProfilMaitreStage, "ProfilMaitreStage"),
            (ProfilRH, "ProfilRH"),
        ]:
            orphelins = modele.objects.exclude(user_id__in=ids_utilisateurs_existants)
            nb = orphelins.count()
            if nb:
                for o in orphelins:
                    self.stdout.write(f"  {label} #{o.pk} -> user_id={o.user_id} (introuvable)")
                if not dry_run:
                    orphelins.delete()
                total += nb

        if total == 0:
            self.stdout.write(self.style.SUCCESS("Aucun profil orphelin trouvé."))
        elif dry_run:
            self.stdout.write(self.style.WARNING(f"\n{total} profil(s) orphelin(s) trouvé(s) (rien supprimé, --dry-run)."))
        else:
            self.stdout.write(self.style.SUCCESS(f"\n{total} profil(s) orphelin(s) supprimé(s)."))
