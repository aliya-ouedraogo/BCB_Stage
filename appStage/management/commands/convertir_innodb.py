from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = (
        "Convertit en InnoDB toutes les tables MySQL actuellement en MyISAM. "
        "MyISAM ignore silencieusement les transactions Django (pas de vrai "
        "rollback en cas d'échec), ce qui peut laisser des enregistrements "
        "à moitié créés en base. Sans effet si la base n'est pas MySQL."
    )

    def handle(self, *args, **options):
        if connection.vendor != 'mysql':
            self.stdout.write(self.style.WARNING(
                "Base de données actuelle : " + connection.vendor + " (pas MySQL) — rien à faire."
            ))
            return

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = DATABASE() AND engine = 'MyISAM'"
            )
            tables = [row[0] for row in cursor.fetchall()]

            if not tables:
                self.stdout.write(self.style.SUCCESS("Aucune table MyISAM trouvée — tout est déjà en InnoDB."))
                return

            self.stdout.write(f"{len(tables)} table(s) en MyISAM à convertir :")
            for nom_table in tables:
                self.stdout.write(f"  - {nom_table}")
                cursor.execute(f"ALTER TABLE `{nom_table}` ENGINE=InnoDB")

        self.stdout.write(self.style.SUCCESS(f"\n{len(tables)} table(s) converties en InnoDB."))
