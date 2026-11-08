/**
 * Invented examples, and the words the example screens need. Field labels, statuses and refusals are the
 * example specs' and messages.ts's own strings. Workbook data stays in the script it was typed in, so Latin
 * names sit in Arabic screens and the reverse, as they do in real files.
 */
import type { Label } from "../src/format.js";

export const TODAY = "2026-11-05";

export const words = {
  firmPay: { fr: "Centre de soutien scolaire", ar: "مركز الدعم المدرسي" },
  firmRep: { fr: "Atelier de réparation", ar: "ورشة التصليح" },
  navStudents: { fr: "Élèves", ar: "التلاميذ" },
  navPay: { fr: "Paiements", ar: "المدفوعات" },
  navParents: { fr: "Parents", ar: "الأولياء" },
  navCash: { fr: "Encaissements", ar: "التحصيل" },
  navCalc: { fr: "Frais de scolarité", ar: "رسوم الدراسة" },
  navRep: { fr: "Réparations", ar: "التصليحات" },
  navShop: { fr: "Atelier", ar: "الورشة" },
  role: { fr: "Propriétaire", ar: "المالك" },
  viewAll: { fr: "Tous les paiements", ar: "كل المدفوعات" },
  viewUnpaid: { fr: "Impayés", ar: "غير المدفوعة" },
  viewLate: { fr: "En retard", ar: "المتأخرة" },
  no: { fr: "N° de reçu", ar: "رقم الوصل" },
  who: { fr: "Payeur", ar: "الدافع" },
  due: { fr: "Échéance", ar: "تاريخ الاستحقاق" },
  amt: { fr: "Montant dû", ar: "المبلغ المستحق" },
  paid: { fr: "Montant payé", ar: "المبلغ المدفوع" },
  rest: { fr: "Reste à payer", ar: "المتبقي" },
  state: { fr: "État", ar: "الحالة" },
  filter: { fr: "Filtrer", ar: "تصفية" },
  export: { fr: "Exporter vers Excel", ar: "تصدير إلى Excel" },
  import: { fr: "Importer un fichier Excel", ar: "استيراد ملف Excel" },
  addPay: { fr: "Nouveau paiement", ar: "دفعة جديدة" },
  total: { fr: "Total", ar: "المجموع" },
  nPay: { fr: "8 paiements", ar: "8 دفعات" },
  emptyTitle: { fr: "Aucun paiement pour l’instant", ar: "لا توجد دفعات بعد" },
  emptyBody: { fr: "Ajoutez le premier, ou importez un fichier Excel si vos paiements y sont déjà.", ar: "أضف أول دفعة، أو استورد ملف Excel إذا كانت دفعاتك فيه." },
  repForm: { fr: "Fiche de réparation", ar: "بطاقة التصليح" },
  secClient: { fr: "Client", ar: "الزبون" },
  secJob: { fr: "Travail", ar: "العمل" },
  customer: { fr: "Client", ar: "الزبون" },
  phone: { fr: "Téléphone", ar: "الهاتف" },
  device: { fr: "Appareil", ar: "الجهاز" },
  problem: { fr: "Panne", ar: "العطل" },
  assignee: { fr: "Technicien", ar: "التقني" },
  received: { fr: "Reçu le", ar: "تاريخ الاستلام" },
  promised: { fr: "Promis pour le", ar: "الموعد المتفق عليه" },
  price: { fr: "Prix", ar: "السعر" },
  parts: { fr: "Coût des pièces", ar: "تكلفة القطع" },
  margin: { fr: "Marge", ar: "الهامش" },
  save: { fr: "Enregistrer", ar: "حفظ" },
  cancel: { fr: "Annuler", ar: "إلغاء" },
  edit: { fr: "Modifier", ar: "تعديل" },
  badPhone: { fr: "Entrez un numéro de téléphone algérien.", ar: "أدخل رقم هاتف جزائري." },
  addRep: { fr: "Nouvelle réparation", ar: "تصليح جديد" },
  boardView: { fr: "Tableau", ar: "اللوحة" },
  repAll: { fr: "Toutes les réparations", ar: "كل التصليحات" },
  refused: { fr: "Les conditions de cette action ne sont pas remplies.", ar: "شروط هذا الإجراء غير مستوفاة." },
  refusedOf: { fr: "Marquer prêt refusé", ar: "تعذّر «تحديد كجاهز»" },
  start_repair: { fr: "Commencer", ar: "بدء التصليح" },
  mark_ready: { fr: "Marquer prêt", ar: "تحديد كجاهز" },
  deliver: { fr: "Livrer", ar: "تسليم" },
  history: { fr: "Historique", ar: "سجل التعديلات" },
  revert: { fr: "Annuler cette modification", ar: "إلغاء هذا التعديل" },
  created: { fr: "Créé", ar: "أُنشئ" },
  srcUi: { fr: "Interface", ar: "الواجهة" },
  srcFlow: { fr: "Suivi", ar: "المسار" },
  kpiDue: { fr: "Total à encaisser", ar: "إجمالي المستحقات" },
  kpiDueNote: { fr: "5 paiements ouverts", ar: "5 دفعات مفتوحة" },
  kpiLate: { fr: "Dont en retard", ar: "منها متأخرة" },
  kpiMonth: { fr: "Encaissé en novembre, au 5", ar: "المحصل في نوفمبر، إلى يوم 5" },
  chartPaid: { fr: "Encaissé par mois", ar: "المحصل حسب الشهر" },
  chartState: { fr: "Par état", ar: "حسب الحالة" },
  month: { fr: "Mois", ar: "الشهر" },
  calcSubject: { fr: "Prix par matière", ar: "سعر المادة" },
  calcCount: { fr: "Nombre de matières", ar: "عدد المواد" },
  calcSiblings: { fr: "Frères et sœurs inscrits", ar: "عدد الإخوة المسجلين" },
  calcRate: { fr: "Taux de remise", ar: "نسبة التخفيض" },
  calcTotal: { fr: "Total à payer", ar: "المبلغ الإجمالي" },
  compute: { fr: "Calculer", ar: "احسب" },
  result: { fr: "Résultat", ar: "النتيجة" },
  setupTitle: { fr: "Créer le compte propriétaire", ar: "إنشاء حساب المالك" },
  setupIntro: { fr: "C’est le premier démarrage. Le premier compte créé est celui du propriétaire, avec tous les droits.", ar: "هذا أول تشغيل للتطبيق. أول حساب يُنشأ هو حساب المالك، وله كل الصلاحيات." },
  user: { fr: "Nom d’utilisateur", ar: "اسم المستخدم" },
  pass: { fr: "Mot de passe", ar: "كلمة المرور" },
  passHint: { fr: "Au moins 10 caractères", ar: "10 أحرف على الأقل" },
  createAccount: { fr: "Créer le compte", ar: "إنشاء الحساب" },
  secOther: { fr: "Autres pages", ar: "صفحات أخرى" },
  secAccount: { fr: "Compte", ar: "الحساب" },
  language: { fr: "Langue", ar: "اللغة" },
  theme: { fr: "Apparence", ar: "المظهر" },
  themeAuto: { fr: "Comme l’appareil", ar: "حسب الجهاز" },
  logout: { fr: "Se déconnecter", ar: "تسجيل الخروج" },
  file: { fr: "Paiements_2026.xlsx", ar: "Paiements_2026.xlsx" },
  previewApp: { fr: "Aperçu de l’application", ar: "معاينة التطبيق" },
  decided: { fr: "5 décisions sur 31", ar: "5 قرارات من 31" },
  lowFirst: { fr: "Les moins sûres d’abord", ar: "الأقل ثقة أولا" },
  bulk: { fr: "Accepter les 12 propositions à confiance élevée", ar: "قبول الاقتراحات عالية الثقة (12)" },
  accept: { fr: "Accepter", ar: "قبول" },
  reject: { fr: "Rejeter", ar: "رفض" },
  accepted: { fr: "Accepté", ar: "مقبول" },
  lgHeader: { fr: "Titres", ar: "العناوين" },
  lgTotal: { fr: "Total", ar: "المجموع" },
  lgEvidence: { fr: "Preuve de cette proposition", ar: "دليل هذا الاقتراح" },
  lgFlagged: { fr: "Cellule à vérifier", ar: "خلية للتحقق" },
  kAnomaly: { fr: "Formule à vérifier", ar: "صيغة للتحقق" },
  kEntity: { fr: "Une seule liste", ar: "قائمة واحدة" },
  kChoice: { fr: "Liste de choix", ar: "قائمة اختيارات" },
  kPeriod: { fr: "Feuilles mensuelles", ar: "أوراق شهرية" },
  kTotal: { fr: "Ligne de total", ar: "صف المجموع" },
  kComputed: { fr: "Colonne calculée", ar: "عمود محسوب" },
  studio: { fr: "Daftar Studio", ar: "دفتر ستوديو" },
  projects: { fr: "Projets", ar: "المشاريع" },
  newProject: { fr: "Nouveau projet", ar: "مشروع جديد" },
  workbook: { fr: "Fichier Excel", ar: "ملف Excel" },
  workbookHint: { fr: "xlsx, xlsm, xls, ods ou csv, jusqu’à 25 Mo", ar: "xlsx أو xlsm أو xls أو ods أو csv، حتى 25 ميغابايت" },
  analyse: { fr: "Analyser", ar: "تحليل" },
  analysing: { fr: "Analyse en cours :", ar: "جارٍ تحليل:" },
  uploadFailed: { fr: "Ce fichier n’a pas pu être analysé", ar: "تعذر تحليل هذا الملف" },
  uploadUnreadable: { fr: "Impossible de lire ce fichier. Il est peut-être endommagé.", ar: "تعذرت قراءة هذا الملف. ربما يكون تالفا." },
  projectList: { fr: "Projets en cours", ar: "المشاريع الجارية" },
  projectName: { fr: "Projet", ar: "المشروع" },
  fileName: { fr: "Fichier", ar: "الملف" },
  updated: { fr: "Modifié le", ar: "آخر تعديل" },
  pendingCount: { fr: "À décider", ar: "دون قرار" },
  decidedCount: { fr: "Décidés", ar: "محسومة" },
  reportTitle: { fr: "Rapport de génération", ar: "تقرير الإنشاء" },
  reportSummary: { fr: "3 listes et 312 lignes générées", ar: "أُنشئت 3 قوائم و312 صفا" },
  modelTitle: { fr: "Le modèle n’a pas pu être joint", ar: "تعذر الوصول إلى النموذج" },
  modelBody: { fr: "Les noms et les choix serrés viennent des seules règles. Vous pouvez relancer l’analyse quand le modèle répond.", ar: "الأسماء والخيارات المتقاربة مبنية على القواعد فقط. يمكنك إعادة التحليل عندما يستجيب النموذج." },
  rerun: { fr: "Relancer l’analyse", ar: "إعادة التحليل" },
  seriesTitle: { fr: "2 colonnes ne seront pas calculées", ar: "لن يُحسب عمودان" },
  seriesBody: { fr: "Une même formule doit valoir pour tous les mois. Si une feuille ne la suit pas, la colonne n’est plus calculée, pour aucun mois. Les anciennes valeurs restent justes, mais il faudra saisir cette colonne à la main sur les nouvelles lignes. Corrigez la feuille, puis relancez l’analyse.", ar: "يجب أن تصلح الصيغة نفسها لكل الأشهر. إذا لم تتبعها ورقة واحدة، يتوقف حساب العمود في كل الأشهر. تبقى القيم القديمة صحيحة، لكن يجب كتابة هذا العمود يدويا في الصفوف الجديدة. صحح الورقة، ثم أعد التحليل." },
  colField: { fr: "Colonne", ar: "العمود" },
  colTab: { fr: "Feuille", ar: "الورقة" },
  colReason: { fr: "Raison", ar: "السبب" },
  columnMissing: { fr: "Cette feuille n’a pas cette colonne.", ar: "هذه الورقة ليس فيها هذا العمود." },
  notAFormula: { fr: "Cette feuille a des valeurs saisies à la place de la formule.", ar: "في هذه الورقة قيم مكتوبة بدل الصيغة." },
  differentFormula: { fr: "La formule de cette feuille est différente.", ar: "صيغة هذه الورقة مختلفة." },
  parityTitle: { fr: "Résultats différents de ceux d’Excel", ar: "نتائج تختلف عن نتائج Excel" },
  colFormula: { fr: "Formule", ar: "الصيغة" },
  colCells: { fr: "Cellules", ar: "الخلايا" },
  badValuesTitle: { fr: "Valeurs non reprises", ar: "قيم لم تُنقل" },
  colCell: { fr: "Cellule", ar: "الخلية" },
  colType: { fr: "Attendu", ar: "المطلوب" },
  typeDate: { fr: "Une date", ar: "تاريخ" },
  typeMoney: { fr: "Un montant", ar: "مبلغ" },
  questionsTitle: { fr: "Questions à régler", ar: "أسئلة تحتاج إلى جواب" },
  questionYear: { fr: "Quelle année pour la feuille Mars ?", ar: "أي سنة تخص الورقة مارس؟" },
  questionYearHint: { fr: "Cette feuille reste hors de l’application tant que l’année n’est pas donnée.", ar: "تبقى هذه الورقة خارج التطبيق حتى تُحدَّد السنة." },
  saveAnswer: { fr: "Enregistrer la réponse", ar: "حفظ الجواب" },
} as const satisfies Record<string, Label>;

export type Word = keyof typeof words;

export const statuses = {
  paid: { color: "#2f9e60", fr: "Payé", ar: "مدفوع" },
  partial: { color: "#e0a030", fr: "Partiel", ar: "جزئي" },
  unpaid: { color: "#d64545", fr: "Impayé", ar: "غير مدفوع" },
  review: { color: "#FFF3B0", fr: "À vérifier par le comptable", ar: "للمراجعة من طرف المحاسب" },
  hold: { color: "#111111", fr: "Bloqué", ar: "موقوف" },
  received: { color: "#6b7280", fr: "Reçu", ar: "مستلم" },
  in_repair: { color: "#e0a030", fr: "En réparation", ar: "قيد التصليح" },
  ready: { color: "#3b82f6", fr: "Prêt", ar: "جاهز" },
  delivered: { color: "#2f9e60", fr: "Livré", ar: "مسلّم" },
} as const;

export type StatusKey = keyof typeof statuses;

export interface Payment {
  no: string;
  who: string;
  due: string | null;
  amount: number;
  paid: number;
  status: StatusKey;
  rest: number;
  late: boolean;
}

const payment = (no: string, who: string, due: string | null, amount: number, paid: number, status: StatusKey): Payment => ({ no, who, due, amount, paid, status, rest: amount - paid, late: status !== "paid" && !!due && due < TODAY });

export const payments: Payment[] = [
  payment("R-0412", "Benali Samir", "2026-11-03", 18500, 18500, "paid"),
  payment("R-0413", "حورية سعيدي", "2026-11-08", 12000, 5000, "partial"),
  payment("R-0414", "Meziane Sofiane", "2026-11-01", 24750, 0, "unpaid"),
  payment("R-0415", "أمين شريف", "2026-11-10", 9600, 9600, "paid"),
  payment("R-0416", "Haddad Lynda", "2026-10-28", 31200, 15000, "partial"),
  payment("R-0417", "وليد خليفي", "2026-11-12", 6800, 0, "unpaid"),
  payment("R-0418", "Établissement Frères Benyoucef", "2026-11-15", 146000, 100000, "partial"),
  payment("R-0419", "أمال بن سالم", "2026-11-15", 4200, 4200, "paid"),
];

/** Long names, big amounts, a missing date, and pale and black status colours. */
export const awkwardPayments: Payment[] = [
  payment("FACT-2026/00012345", "Établissement Frères Benyoucef et Associés pour la Distribution de Pièces Détachées", "2026-11-03", 123456789, 123456789, "paid"),
  payment("R-0413", "شركة الإخوة بن يوسف وشركاؤهم لتوزيع قطع الغيار والمعدات الفلاحية", "2026-11-08", 1234567.89, 5000, "review"),
  payment("R-0414", "M. O’Brien-Hadj Ali", null, 24750, 0, "hold"),
  payment("R-0415", "أمين", "2026-10-01", 0.5, 0, "unpaid"),
];

export const sumOf = (rows: Payment[]): { amount: number; paid: number; rest: number } =>
  rows.reduce((sum, row) => ({ amount: sum.amount + row.amount, paid: sum.paid + row.paid, rest: sum.rest + row.rest }), { amount: 0, paid: 0, rest: 0 });

export interface Repair {
  no: string;
  device: string;
  who: string;
  status: StatusKey;
  promised?: string;
  next?: "start_repair" | "mark_ready" | "deliver";
  refused?: boolean;
}

export const repairs: Repair[] = [
  { no: "REP-0231", device: "Samsung A15", who: "Benali Samir", status: "in_repair", promised: "2026-11-06", next: "mark_ready" },
  { no: "REP-0232", device: "Redmi Note 13", who: "حورية سعيدي", status: "ready", promised: "2026-11-05", next: "deliver" },
  { no: "REP-0233", device: "Condor Plume L8", who: "أمين شريف", status: "received", promised: "2026-11-07", next: "start_repair" },
  { no: "REP-0234", device: "iPhone 11", who: "Haddad Lynda", status: "in_repair", promised: "2026-11-04", next: "mark_ready" },
  { no: "REP-0235", device: "HP 250 G8", who: "وليد خليفي", status: "delivered", promised: "2026-11-02" },
  { no: "REP-0236", device: "Samsung TV 43", who: "Meziane Sofiane", status: "in_repair", promised: "2026-11-12", next: "mark_ready", refused: true },
];

export const awkwardRepairs: Repair[] = [
  { no: "REP-2026-000231", device: "Climatiseur mural Condor 12000 BTU Inverter avec télécommande", who: "شركة الإخوة بن يوسف وشركاؤهم لتوزيع قطع الغيار", status: "in_repair", promised: "2026-11-04", next: "mark_ready", refused: true },
  { no: "REP-0232", device: "X", who: "Établissement Frères Benyoucef et Associés", status: "ready", next: "deliver" },
  { no: "REP-0233", device: "غسالة", who: "أمين", status: "in_repair", promised: "2026-11-07", next: "mark_ready" },
];

export const months: [string, number][] = [
  ["2026-06", 96000],
  ["2026-07", 118500],
  ["2026-08", 87200],
  ["2026-09", 134600],
  ["2026-10", 141900],
  ["2026-11", 152300],
];

/**
 * Takings by date, the way `/aggregate` returns them: one point per date with data, up to 500 of them. So
 * weekends and a closed month are missing, one day is a net refund, and one is a sum over blanks.
 */
export const takings: [string, number | null][] = Array.from({ length: 240 }, (_, index) => {
  const offset = index + Math.floor(index / 5) * 2 + (index > 120 ? 30 : 0);
  const date = new Date(Date.UTC(2026, 0, 1 + offset)).toISOString().slice(0, 10);
  if (index === 90) return [date, -18000];
  if (index === 160) return [date, null];
  return [date, 20000 + ((index * 7919) % 13) * 3000];
});

export interface Project {
  id: string;
  name: string;
  file: string;
  updated: string;
  pending: number;
  decided: number;
}

export const projects: Project[] = [
  { id: "a", name: "Centre de soutien", file: "Paiements_2026.xlsx", updated: "2026-11-05", pending: 26, decided: 5 },
  { id: "b", name: "ورشة التصليح", file: "تصليحات.xlsx", updated: "2026-11-03", pending: 0, decided: 18 },
];

export const awkwardProjects: Project[] = [
  { id: "a", name: "Établissement Frères Benyoucef et Associés pour la Distribution de Pièces Détachées", file: "Etablissement_Freres_Benyoucef_Paiements_Annuels_2026_version_finale_definitive.xlsx", updated: "2026-11-05", pending: 1234, decided: 5678 },
  { id: "b", name: "شركة الإخوة بن يوسف وشركاؤهم لتوزيع قطع الغيار والمعدات الفلاحية", file: "ملف_المدفوعات_السنوية_النسخة_النهائية_2026.xlsx", updated: "2026-11-03", pending: 0, decided: 0 },
];

/** `seriesFormulas` from a generation report, with the labels #19 asks for. Reasons are words in `words`. */
export interface SeriesProblem {
  field: string;
  tab: string;
  reason: "columnMissing" | "notAFormula" | "differentFormula";
}

export const seriesProblems: SeriesProblem[] = [
  { field: "Reste à payer", tab: "Mars", reason: "notAFormula" },
  { field: "المبلغ الصافي", tab: "فيفري", reason: "differentFormula" },
];

export const awkwardSeriesProblems: SeriesProblem[] = [
  { field: "Montant total hors taxes après remise commerciale et frais de dossier", tab: "Récapitulatif du premier trimestre", reason: "columnMissing" },
  { field: "المبلغ الصافي بعد الخصم التجاري ومصاريف الملف", tab: "ملخص الثلاثي الأول من السنة المالية", reason: "differentFormula" },
];

export interface ParityProblem {
  tab: string;
  formula: string;
  cells: string[];
}

export const parityProblems: ParityProblem[] = [{ tab: "Calcul", formula: "=SUMPRODUCT(D3:D9,E3:E9)", cells: ["F4", "F7"] }];

export const awkwardParityProblems: ParityProblem[] = [{ tab: "Récapitulatif du premier trimestre", formula: "=SUMPRODUCT((Clients!$A$2:$A$500=A3)*(Clients!$D$2:$D$500>0),Clients!$F$2:$F$500)/COUNTIF(Clients!$A$2:$A$500,A3)", cells: ["F4", "F7", "F9", "F12", "F15", "F18", "F21", "F24", "F27", "F30"] }];

export interface BadValue {
  tab: string;
  cell: string;
  field: string;
  expected: "typeDate" | "typeMoney";
}

export const badValues: BadValue[] = [
  { tab: "Janvier", cell: "C14", field: "Échéance", expected: "typeDate" },
  { tab: "مارس", cell: "D3", field: "المبلغ", expected: "typeMoney" },
];
