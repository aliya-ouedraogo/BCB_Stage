/**
 * Indicateur de chargement générique pour les formulaires, partagé par
 * toutes les pages (auth et tableau de bord) : tout
 * <form class="form-avec-chargement"> affiche un spinner sur son bouton
 * de soumission et le désactive visuellement pendant l'envoi, pour que
 * l'utilisateur sache que sa demande est bien partie (connexion,
 * activation de compte, acceptation/refus de candidature, etc.).
 *
 * Le texte affiché pendant le chargement vient de l'attribut
 * data-loading-text du bouton, sinon un texte par défaut est utilisé.
 *
 * Écouté au niveau de `document` (délégation) plutôt que sur chaque
 * formulaire individuellement : reste valable même après un remplacement
 * de page par htmx (boost), qui peut réinjecter de nouveaux formulaires
 * sans que ce script soit ré-exécuté.
 */
(function () {
  function texteDeChargement(bouton) {
    return bouton.dataset.loadingText || 'Veuillez patienter…';
  }

  document.addEventListener('submit', function (evenement) {
    var form = evenement.target;
    if (!(form instanceof HTMLFormElement)) return;
    if (!form.classList.contains('form-avec-chargement')) return;

    // Le navigateur ne déclenche 'submit' que si la validation native du
    // formulaire est passée : à ce stade la requête va bien partir.
    var bouton = form.querySelector('[type="submit"]');
    if (!bouton || bouton.dataset.chargementActif === '1') return;
    bouton.dataset.chargementActif = '1';
    bouton.disabled = true;
    bouton.classList.add('is-loading');
    bouton.innerHTML = '<span class="btn-spinner"></span> ' + texteDeChargement(bouton);
  });
})();
