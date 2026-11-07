/** The app's own words. Everything else comes from the spec or the server. */
import { useDaftar, type Label } from "@daftar/ui";

const words = {
  setupTitle: { fr: "Créer le compte propriétaire", ar: "إنشاء حساب المالك" },
  setupIntro: { fr: "C’est le premier démarrage. Le premier compte créé est celui du propriétaire, avec tous les droits.", ar: "هذا أول تشغيل للتطبيق. أول حساب يُنشأ هو حساب المالك، وله كل الصلاحيات." },
  createAccount: { fr: "Créer le compte", ar: "إنشاء الحساب" },
  signInTitle: { fr: "Se connecter", ar: "تسجيل الدخول" },
  signIn: { fr: "Se connecter", ar: "دخول" },
  signOut: { fr: "Se déconnecter", ar: "تسجيل الخروج" },
  username: { fr: "Nom d’utilisateur", ar: "اسم المستخدم" },
  password: { fr: "Mot de passe", ar: "كلمة المرور" },
  passwordHint: { fr: "Au moins 10 caractères", ar: "10 أحرف على الأقل" },
  previewTitle: { fr: "Cet aperçu a été fermé", ar: "أُغلقت هذه المعاينة" },
  previewBody: { fr: "Rouvrez-le depuis le Studio.", ar: "أعد فتحها من الاستوديو." },
  add: { fr: "Ajouter", ar: "إضافة" },
  save: { fr: "Enregistrer", ar: "حفظ" },
  cancel: { fr: "Annuler", ar: "إلغاء" },
  total: { fr: "Total", ar: "المجموع" },
  yes: { fr: "Oui", ar: "نعم" },
  no: { fr: "Non", ar: "لا" },
  none: { fr: "Aucun", ar: "بدون" },
  choose: { fr: "Choisir…", ar: "اختر…" },
  emptyTitle: { fr: "Rien pour l’instant", ar: "لا شيء بعد" },
  emptyBody: { fr: "Ajoutez le premier élément.", ar: "أضف العنصر الأول." },
  emptyReadOnly: { fr: "Rien n’a encore été ajouté ici.", ar: "لم يُضف أي شيء هنا بعد." },
  noResultsTitle: { fr: "Aucun résultat", ar: "لا توجد نتائج" },
  noResultsBody: { fr: "Essayez une autre recherche, ou un autre onglet.", ar: "جرّب بحثا آخر أو تبويبا آخر." },
  nothingToShowTitle: { fr: "Rien à afficher", ar: "لا شيء للعرض" },
  nothingToShowBody: { fr: "Votre compte n’a accès à aucune liste.", ar: "ليس لحسابك وصول إلى أي قائمة." },
  pages: { fr: "Pages", ar: "الصفحات" },
  account: { fr: "Compte", ar: "الحساب" },
  otherPages: { fr: "Autres pages", ar: "صفحات أخرى" },
  language: { fr: "Langue", ar: "اللغة" },
  previous: { fr: "Précédent", ar: "السابق" },
  next: { fr: "Suivant", ar: "التالي" },
  failedTitle: { fr: "Le serveur ne répond pas", ar: "الخادم لا يستجيب" },
  failedBody: { fr: "Vérifiez la connexion, puis réessayez.", ar: "تحقق من الاتصال ثم أعد المحاولة." },
  retry: { fr: "Réessayer", ar: "إعادة المحاولة" },
  refusedTitle: { fr: "Action refusée", ar: "تم رفض الإجراء" },
  refusedBody: { fr: "Votre compte n’a pas ce droit.", ar: "ليس لحسابك هذا الحق." },
  missingTitle: { fr: "Page introuvable", ar: "الصفحة غير موجودة" },
  missingBody: { fr: "Cette page n’existe pas, ou votre compte n’y a pas accès.", ar: "هذه الصفحة غير موجودة، أو ليس لحسابك وصول إليها." },
  goHome: { fr: "Retour à l’accueil", ar: "العودة إلى الرئيسية" },
  couldNotSave: { fr: "L’enregistrement n’a pas abouti", ar: "لم يتم الحفظ" },
  edit: { fr: "Modifier", ar: "تعديل" },
  delete: { fr: "Supprimer", ar: "حذف" },
  deleteQuestion: { fr: "Supprimer cet élément ?", ar: "حذف هذا العنصر؟" },
  deleteUndoable: { fr: "Vous pourrez le restaurer depuis cette page.", ar: "يمكنك استرجاعه من هذه الصفحة." },
  deleteFinal: { fr: "Seul un compte autorisé pourra le restaurer.", ar: "لن يتمكن من استرجاعه إلا حساب مخوّل." },
  deleteYes: { fr: "Oui, supprimer", ar: "نعم، احذف" },
  deleteNo: { fr: "Non, le garder", ar: "لا، أبقِه" },
  deletedTitle: { fr: "Cet élément a été supprimé", ar: "حُذف هذا العنصر" },
  restore: { fr: "Restaurer", ar: "استرجاع" },
  history: { fr: "Historique", ar: "سجل التعديلات" },
  historyEmpty: { fr: "Aucun historique conservé.", ar: "لا يوجد سجل محفوظ." },
  created: { fr: "Créé", ar: "أُنشئ" },
  deleted: { fr: "Supprimé", ar: "حُذف" },
  restored: { fr: "Restauré", ar: "استُرجع" },
  undo: { fr: "Annuler cette modification", ar: "إلغاء هذا التعديل" },
  undone: { fr: "Annulée", ar: "أُلغي" },
  undoLine: { fr: "Annulation d’une modification", ar: "إلغاء تعديل" },
  hiddenChanged: { fr: "Un champ masqué a changé", ar: "تغيّر حقل مخفي" },
  sourceUi: { fr: "Interface", ar: "الواجهة" },
  sourceWorkflow: { fr: "Suivi", ar: "المسار" },
  sourceImport: { fr: "Import", ar: "استيراد" },
  sourceSystem: { fr: "Système", ar: "النظام" },
} as const satisfies Record<string, Label>;

export type Word = keyof typeof words;

export function useWords(): (word: Word) => string {
  const { say } = useDaftar();
  return (word) => say(words[word]);
}

/** A message with its field's name, for the summary: a server's "required" says nothing without it. */
export function aboutField(field: string, message: string, locale: string): string {
  return locale === "ar-DZ" ? `${field}: ${message}` : `${field}\u00a0: ${message}`;
}

/** A field's name before what's said about it, in a history line. */
export function withColon(label: string, locale: string): string {
  return locale === "ar-DZ" ? `${label}:` : `${label}\u00a0:`;
}

/** The heading over why a step didn't go through. */
export function refusedOf(step: string, locale: string): string {
  return locale === "ar-DZ" ? `تعذّر «${step}»` : `«\u00a0${step}\u00a0» refusé`;
}

/** Where to look after a condition wasn't met: the fields it reads. */
export function fieldsToLookAt(labels: readonly string[], locale: string): string {
  return locale === "ar-DZ" ? `يرجى التحقق من: ${labels.join("، ")}` : `À vérifier\u00a0: ${labels.join(", ")}`;
}

/** Where a long list has got to: "1–50 sur 120". */
export function rangeOf(first: number, last: number, total: number, locale: string): string {
  return locale === "ar-DZ" ? `${first}–${last} من ${total}` : `${first}–${last} sur ${total}`;
}
