# Generated manually for BCBStageFlow — rôle Directeur + Notifications.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('appStage', '0006_presence_note_activite'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.CharField(
                choices=[
                    ('STAGIAIRE', 'Stagiaire'),
                    ('RH', 'Ressources Humaines'),
                    ('MAITRE_STAGE', 'Maître de Stage'),
                    ('DIRECTEUR', 'Directeur de Service'),
                ],
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name='ProfilDirecteur',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('poste', models.CharField(blank=True, max_length=150)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='profil_directeur', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddField(
            model_name='departement',
            name='directeur',
            field=models.OneToOneField(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='departement', to='appStage.profildirecteur',
            ),
        ),
        migrations.AddField(
            model_name='demandeencadrement',
            name='proposee_par',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='propositions_encadrement', to='appStage.profildirecteur',
                help_text="Directeur de service à l'origine de la proposition.",
            ),
        ),
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('message', models.CharField(max_length=255)),
                ('lien', models.CharField(blank=True, help_text='Chemin relatif vers lequel rediriger au clic.', max_length=255)),
                ('lu', models.BooleanField(default=False)),
                ('date_creation', models.DateTimeField(auto_now_add=True)),
                ('destinataire', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-date_creation'],
            },
        ),
    ]
