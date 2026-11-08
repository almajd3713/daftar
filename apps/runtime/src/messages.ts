/** What users read when something is refused. Written for a shop owner, not a developer. */
export interface Message {
  fr: string;
  ar: string;
}

/** Undoing has no form to show a field's error on, so this says in a sentence which value is in the way. */
export function valueTaken(field: Message): Message {
  return {
    fr: `Un autre élément utilise déjà cette valeur de «\u00a0${field.fr}\u00a0». Changez-la sur cet autre élément, puis réessayez.`,
    ar: `عنصر آخر يستعمل هذه القيمة في «${field.ar}». غيّرها في ذلك العنصر ثم أعد المحاولة.`,
  };
}

export const MESSAGES = {
  workerUnavailable: { fr: "Le service Excel ne répond pas. Réessayez dans un instant.", ar: "خدمة Excel لا تستجيب. أعد المحاولة بعد قليل." },
  required: { fr: "Ce champ est obligatoire.", ar: "هذا الحقل إجباري." },
  unknownField: { fr: "Ce champ n'existe pas.", ar: "هذا الحقل غير موجود." },
  readOnly: { fr: "Ce champ est calculé ou ne peut pas être modifié ici.", ar: "هذا الحقل محسوب أو لا يمكن تعديله هنا." },
  notAllowed: { fr: "Vous n'avez pas le droit de modifier ce champ.", ar: "لا يحق لك تعديل هذا الحقل." },
  invalidNumber: { fr: "Entrez un nombre.", ar: "أدخل رقما." },
  invalidInteger: { fr: "Entrez un nombre entier.", ar: "أدخل عددا صحيحا." },
  invalidDate: { fr: "Entrez une date valide.", ar: "أدخل تاريخا صحيحا." },
  invalidText: { fr: "Entrez un texte.", ar: "أدخل نصا." },
  invalidBoolean: { fr: "Choisissez oui ou non.", ar: "اختر نعم أو لا." },
  invalidChoice: { fr: "Choisissez une valeur de la liste.", ar: "اختر قيمة من القائمة." },
  invalidPhone: { fr: "Entrez un numéro de téléphone algérien.", ar: "أدخل رقم هاتف جزائري." },
  invalidEmail: { fr: "Entrez une adresse e-mail valide.", ar: "أدخل بريدا إلكترونيا صحيحا." },
  invalidLink: { fr: "Cet élément n'existe pas.", ar: "هذا العنصر غير موجود." },
  notUnique: { fr: "Cette valeur existe déjà.", ar: "هذه القيمة موجودة من قبل." },
  useTransition: { fr: "Changez l'état avec les actions prévues.", ar: "غيّر الحالة بالإجراءات المتاحة." },
  stale: { fr: "Quelqu'un a modifié cet élément entre-temps. Rechargez puis réessayez.", ar: "عدّل شخص آخر هذا العنصر في الأثناء. أعد التحميل ثم حاول مجددا." },
  linked: { fr: "D'autres éléments dépendent de celui-ci, il ne peut pas être supprimé.", ar: "عناصر أخرى تعتمد على هذا العنصر، لذا لا يمكن حذفه." },
  transitionFrom: { fr: "Cette action n'est pas possible depuis l'état actuel.", ar: "هذا الإجراء غير ممكن من الحالة الحالية." },
  transitionCondition: { fr: "Les conditions de cette action ne sont pas remplies.", ar: "شروط هذا الإجراء غير مستوفاة." },
  transitionRole: { fr: "Votre rôle ne permet pas cette action.", ar: "دورك لا يسمح بهذا الإجراء." },
  revertConflict: { fr: "Ces valeurs ont changé depuis. Cette modification ne peut plus être annulée.", ar: "تغيرت هذه القيم منذ ذلك الحين. لم يعد ممكنا إلغاء هذا التعديل." },
  wrongPassword: { fr: "Ce mot de passe n'est pas le bon.", ar: "كلمة المرور هذه غير صحيحة." },
  cannotRemoveSelf: { fr: "Vous ne pouvez pas supprimer votre propre compte.", ar: "لا يمكنك حذف حسابك الخاص." },
  useOwnPassword: { fr: "Changez votre propre mot de passe depuis votre compte.", ar: "غيّر كلمة مرورك من حسابك." },
  alreadyReverted: { fr: "Cette modification a déjà été annulée.", ar: "أُلغي هذا التعديل من قبل." },
  setupDone: { fr: "Le compte propriétaire existe déjà.", ar: "حساب المالك موجود من قبل." },
  badLogin: { fr: "Nom d'utilisateur ou mot de passe incorrect.", ar: "اسم المستخدم أو كلمة المرور غير صحيحة." },
  weakPassword: { fr: "Le mot de passe doit contenir au moins 10 caractères.", ar: "يجب أن تحتوي كلمة المرور على 10 أحرف على الأقل." },
  throttled: { fr: "Trop d'essais. Réessayez dans quelques minutes.", ar: "محاولات كثيرة. حاول مجددا بعد بضع دقائق." },
} satisfies Record<string, Message>;
