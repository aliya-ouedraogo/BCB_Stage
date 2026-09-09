from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import ProfilDirecteur, ProfilMaitreStage, ProfilRH, User


@receiver(post_save, sender=User)
def creer_profil_automatiquement(sender, instance, created, **kwargs):
    """
    Quand un compte RH, Maître de Stage ou Directeur est créé (typiquement
    via /admin/ par l'équipe technique), son profil associé est créé
    automatiquement — sinon l'app plante en cherchant `user.profil_rh`,
    `user.profil_maitre_stage` ou `user.profil_directeur` qui n'existerait
    pas encore.

    Le profil Stagiaire N'EST PAS créé ici intentionnellement : il l'est
    déjà explicitement par Candidature.accepter(), en même temps que le
    Stage — un stagiaire n'a de sens qu'accompagné d'un stage réel.
    """
    if not created:
        return

    if instance.role == User.Role.RH:
        ProfilRH.objects.get_or_create(user=instance)
    elif instance.role == User.Role.MAITRE_STAGE:
        ProfilMaitreStage.objects.get_or_create(user=instance)
    elif instance.role == User.Role.DIRECTEUR:
        ProfilDirecteur.objects.get_or_create(user=instance)
