/** The few words the components need for themselves. Everything else comes from the spec or the server. */
import type { Label } from "./format.js";

export const uiText = {
  late: { fr: "En retard", ar: "متأخر" },
  search: { fr: "Rechercher", ar: "بحث" },
  back: { fr: "Retour", ar: "رجوع" },
  menu: { fr: "Menu", ar: "القائمة" },
  more: { fr: "Plus", ar: "المزيد" },
  skipToContent: { fr: "Aller au contenu", ar: "الانتقال إلى المحتوى" },
  seeNumbers: { fr: "Voir les chiffres", ar: "عرض الأرقام" },
  showPassword: { fr: "Afficher", ar: "إظهار" },
  hidePassword: { fr: "Masquer", ar: "إخفاء" },
  errorPrefix: { fr: "Erreur :", ar: "خطأ:" },
  datePlaceholder: { fr: "jj/mm/aaaa", ar: "يوم/شهر/سنة" },
  previousMonth: { fr: "Mois précédent", ar: "الشهر السابق" },
  nextMonth: { fr: "Mois suivant", ar: "الشهر التالي" },
  previousYear: { fr: "Année précédente", ar: "السنة السابقة" },
  nextYear: { fr: "Année suivante", ar: "السنة التالية" },
  previousYears: { fr: "Années précédentes", ar: "السنوات السابقة" },
  nextYears: { fr: "Années suivantes", ar: "السنوات التالية" },
  chooseFile: { fr: "Choisir un fichier", ar: "اختيار ملف" },
  confidenceLow: { fr: "Confiance faible", ar: "ثقة ضعيفة" },
  confidenceMedium: { fr: "Confiance moyenne", ar: "ثقة متوسطة" },
  confidenceHigh: { fr: "Confiance élevée", ar: "ثقة عالية" },
} as const satisfies Record<string, Label>;

/** How many fields need fixing, for the summary at the top of a form. */
export const fieldsToFix = {
  fr: { one: "{n} champ à corriger", other: "{n} champs à corriger" },
  ar: { one: "يجب تصحيح حقل واحد", two: "يجب تصحيح حقلين", few: "يجب تصحيح {n} حقول", many: "يجب تصحيح {n} حقلا", other: "يجب تصحيح {n} حقل" },
} as const;
