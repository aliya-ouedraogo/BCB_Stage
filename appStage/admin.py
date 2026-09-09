from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    Candidature,
    Departement,
    DemandeEncadrement,
    DocumentStage,
    Entretien,
    Evaluation,
    Mission,
    Notification,
    Presence,
    ProfilDirecteur,
    ProfilMaitreStage,
    ProfilRH,
    ProfilStagiaire,
    RapportHebdomadaire,
    Stage,
    User,
)


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'get_full_name', 'email', 'role', 'is_staff')
    list_filter = ('role', 'is_staff', 'is_active')
    fieldsets = UserAdmin.fieldsets + (
        ('Rôle & contact', {'fields': ('role', 'telephone', 'photo')}),
    )


class ProfilAutoCreeAdmin(admin.ModelAdmin):
    """
    Base pour les profils créés automatiquement (signal post_save pour
    RH/Maître de Stage, ou Candidature.accepter() pour Stagiaire).
    On retire le bouton "Ajouter" : en créer un manuellement ici entre
    en conflit avec celui déjà créé automatiquement pour le même
    utilisateur (contrainte unique sur user_id) — c'est exactement le
    bug "Duplicata du champ ... pour la clef user_id" que ce garde-fou
    empêche désormais.
    """
    def has_add_permission(self, request):
        return False


@admin.register(ProfilStagiaire)
class ProfilStagiaireAdmin(ProfilAutoCreeAdmin):
    pass


@admin.register(ProfilRH)
class ProfilRHAdmin(ProfilAutoCreeAdmin):
    pass


@admin.register(ProfilMaitreStage)
class ProfilMaitreStageAdmin(ProfilAutoCreeAdmin):
    pass


@admin.register(ProfilDirecteur)
class ProfilDirecteurAdmin(ProfilAutoCreeAdmin):
    list_display = ('user', 'poste')


@admin.register(Departement)
class DepartementAdmin(admin.ModelAdmin):
    list_display = ('nom', 'agence', 'directeur')
    search_fields = ('nom', 'agence')


@admin.register(Candidature)
class CandidatureAdmin(admin.ModelAdmin):
    list_display = ('nom_complet', 'poste_souhaite', 'statut', 'departement_affecte', 'date_soumission')
    list_filter = ('statut', 'departement_affecte')
    search_fields = ('nom_complet', 'email', 'poste_souhaite')


@admin.register(Stage)
class StageAdmin(admin.ModelAdmin):
    list_display = ('stagiaire', 'intitule_poste', 'departement', 'maitre_de_stage', 'date_debut', 'date_fin', 'statut', 'avec_soutenance')
    list_filter = ('statut', 'departement', 'avec_soutenance')
    search_fields = ('intitule_poste', 'stagiaire__user__first_name', 'stagiaire__user__last_name')


@admin.register(DemandeEncadrement)
class DemandeEncadrementAdmin(admin.ModelAdmin):
    list_display = ('stage', 'maitre_de_stage_demande', 'proposee_par', 'statut', 'date_demande', 'date_reponse')
    list_filter = ('statut',)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('destinataire', 'message', 'lu', 'date_creation')
    list_filter = ('lu',)


@admin.register(Entretien)
class EntretienAdmin(admin.ModelAdmin):
    list_display = ('stage', 'rh', 'date')
    list_filter = ('rh',)


admin.site.register(Evaluation)
admin.site.register(Mission)
admin.site.register(RapportHebdomadaire)
admin.site.register(Presence)


@admin.register(DocumentStage)
class DocumentStageAdmin(admin.ModelAdmin):
    list_display = ('nom', 'stage', 'type_document', 'statut_signature', 'date_ajout')
    list_filter = ('type_document', 'statut_signature')
