/** Every screen, drawn only from @daftar/ui's components. If a screen needs raw CSS, the system has a gap. */
import { Checkbox } from "@mantine/core";
import { useState, type ReactNode } from "react";

import {
  Amount,
  AppFrame,
  AuthLayout,
  BarList,
  BareFrame,
  BoardCard,
  BoardColumn,
  BoardColumns,
  Button,
  Change,
  ChoiceField,
  CodeText,
  currencyLabel,
  DateField,
  DateText,
  DateTimeText,
  EmptyState,
  ErrorSummary,
  Fact,
  FactList,
  FieldPair,
  FileField,
  Finding,
  FindingList,
  FootRow,
  FormActions,
  FormBody,
  FormSection,
  formatNumber,
  Gutter,
  HeroFigure,
  HistoryList,
  LanguageSwitch,
  LastActions,
  LateTag,
  LeadRow,
  LineChart,
  LongTextField,
  MenuHeading,
  MenuItem,
  MenuList,
  Money,
  MoneyField,
  monthName,
  Notice,
  NumberField,
  Page,
  Panel,
  Panels,
  PasswordField,
  Percent,
  PhoneField,
  PhoneLink,
  PlusIcon,
  RecordList,
  RecordRow,
  ReviewLayout,
  SearchField,
  SheetGrid,
  SheetLegend,
  SheetTabs,
  StateLine,
  Statement,
  StatementLine,
  StatusChip,
  TextField,
  TextLink,
  TwoColumns,
  useDaftar,
  useFrame,
  UserText,
  ViewTabs,
  Waiting,
  type Column,
  type LedgerTableProps,
  type Locale,
  type SheetCell,
  LedgerTable,
} from "../src/index.js";
import {
  awkwardParityProblems,
  awkwardPayments,
  awkwardProjects,
  awkwardRepairs,
  awkwardSeriesProblems,
  badValues,
  months,
  parityProblems,
  payments,
  projects,
  repairs,
  seriesProblems,
  statuses,
  sumOf,
  takings,
  TODAY,
  words,
  type BadValue,
  type ParityProblem,
  type Payment,
  type Project,
  type Repair,
  type SeriesProblem,
  type StatusKey,
  type Word,
} from "./data.js";

export interface ScreenProps {
  awkward: boolean;
  onLocale: (locale: Locale) => void;
}

function useWords(): (word: Word) => string {
  const { say } = useDaftar();
  return (word) => say(words[word]);
}

function Status({ status }: { status: StatusKey }): ReactNode {
  const { say } = useDaftar();
  const entry = statuses[status];
  return <StatusChip color={entry.color} label={say(entry)} />;
}

function payNav(t: (word: Word) => string, awkward: boolean): { key: string; label: ReactNode }[][] {
  return [
    [
      { key: "students", label: t("navStudents") },
      { key: "payments", label: t("navPay") },
      { key: "parents", label: t("navParents") },
    ],
    [
      { key: "cash", label: t("navCash") },
      { key: "calc", label: awkward ? "Frais de scolarité et inscriptions annuelles" : t("navCalc") },
    ],
  ];
}

function repairNav(t: (word: Word) => string): { key: string; label: ReactNode }[][] {
  return [[{ key: "repairs", label: t("navRep") }], [{ key: "workshop", label: t("navShop") }]];
}

function User(): ReactNode {
  const t = useWords();
  return (
    <span>
      <UserText>Samira</UserText> · {t("role")}
    </span>
  );
}

function PayFrame({ current, awkward, onLocale, children }: ScreenProps & { current: string; children: ReactNode }): ReactNode {
  const t = useWords();
  return (
    <AppFrame firm={t("firmPay")} nav={payNav(t, awkward)} current={current} user={<User />} language={<LanguageSwitch onSwitch={onLocale} />}>
      {children}
    </AppFrame>
  );
}

function RepairFrame({ current, onLocale, hideNav, children }: { current: string; onLocale: (locale: Locale) => void; hideNav?: boolean; children: ReactNode }): ReactNode {
  const t = useWords();
  return (
    <AppFrame firm={t("firmRep")} nav={repairNav(t)} current={current} user={<User />} language={<LanguageSwitch onSwitch={onLocale} />} hideNavOnPhone={hideNav}>
      {children}
    </AppFrame>
  );
}

function paymentColumns(t: (word: Word) => string, locale: Locale, hide: string[] = []): Column<Payment>[] {
  const unit = currencyLabel(locale);
  const all: Column<Payment>[] = [
    { key: "no", header: t("no"), nowrap: true, cell: (row) => <TextLink><CodeText>{row.no}</CodeText></TextLink> },
    { key: "who", header: t("who"), cell: (row) => <UserText>{row.who}</UserText> },
    { key: "due", header: t("due"), nowrap: true, cell: (row) => (<><DateText value={row.due} />{row.late ? <> <LateTag /></> : null}</>) },
    { key: "amount", header: t("amt"), unit, numeric: true, cell: (row) => <Amount value={row.amount} /> },
    { key: "paid", header: t("paid"), unit, numeric: true, cell: (row) => <Amount value={row.paid} /> },
    { key: "rest", header: t("rest"), unit, numeric: true, cell: (row) => <Amount value={row.rest} late={row.late} /> },
    { key: "status", header: t("state"), cell: (row) => <Status status={row.status} /> },
  ];
  return all.filter((column) => !hide.includes(column.key));
}

function totalsOf(rows: Payment[]): NonNullable<LedgerTableProps<Payment>["totals"]> {
  const sum = sumOf(rows);
  return { amount: <Amount value={sum.amount} showZero />, paid: <Amount value={sum.paid} showZero />, rest: <Amount value={sum.rest} showZero /> };
}

function ListPage({ awkward, empty }: { awkward: boolean; empty: boolean }): ReactNode {
  const t = useWords();
  const { locale } = useDaftar();
  const { narrow } = useFrame();
  const rows = empty ? [] : awkward ? awkwardPayments : payments;
  const sum = sumOf(rows);
  const views = [
    { key: "all", label: t("viewAll"), count: rows.length },
    { key: "unpaid", label: t("viewUnpaid"), count: rows.filter((row) => row.status !== "paid").length },
    { key: "late", label: t("viewLate"), count: rows.filter((row) => row.late).length },
  ];
  const add = <Button primary leftSection={<PlusIcon />}>{t("addPay")}</Button>;
  const tools = narrow ? <SearchField /> : (<><SearchField /><Button>{t("filter")}</Button></>);
  const tabs = <ViewTabs label={t("navPay")} views={views} current="all" tools={empty ? undefined : tools} />;
  if (empty) {
    return (
      <Page title={t("navPay")}>
        {tabs}
        <EmptyState title={t("emptyTitle")} actions={<>{add}<Button>{t("import")}</Button></>}>{t("emptyBody")}</EmptyState>
      </Page>
    );
  }
  if (narrow) {
    return (
      <Page title={t("navPay")} closing foot={<FootRow totalLabel={t("rest")} total={<Money value={sum.rest} />}>{add}</FootRow>}>
        {tabs}
        <RecordList titleHeading={t("who")} amountHeading={`${t("rest")} (${currencyLabel(locale)})`}>
          {rows.map((row) => (
            <RecordRow
              key={row.no}
              late={row.late}
              title={<UserText>{row.who}</UserText>}
              amount={<Amount value={row.rest} late={row.late} />}
              meta={<><CodeText>{row.no}</CodeText>{row.due ? <> · <DateText value={row.due} /></> : null}{row.late ? <> <LateTag /></> : null}</>}
              status={<Status status={row.status} />}
            />
          ))}
        </RecordList>
      </Page>
    );
  }
  return (
    <Page title={t("navPay")} subtitle={<>{awkward ? null : <>{t("nPay")} · </>}{t("rest")} <Money value={sum.rest} /></>} actions={<><Button>{t("export")}</Button>{add}</>}>
      {tabs}
      <LedgerTable caption={t("viewAll")} columns={paymentColumns(t, locale)} rows={rows} rowKey={(row) => row.no} totalLabel={t("total")} totals={totalsOf(rows)} />
    </Page>
  );
}

export function ListScreen(props: ScreenProps): ReactNode {
  return <PayFrame {...props} current="payments"><ListPage awkward={props.awkward} empty={false} /></PayFrame>;
}

export function EmptyScreen(props: ScreenProps): ReactNode {
  return <PayFrame {...props} current="payments"><ListPage awkward={props.awkward} empty /></PayFrame>;
}

function FormPage(): ReactNode {
  const t = useWords();
  const { narrow } = useFrame();
  const { lang } = useDaftar();
  const actions = (<><Button primary type="submit">{t("save")}</Button><Button>{t("cancel")}</Button></>);
  const [problem, setProblem] = useState("Écran cassé, batterie gonflée");
  return (
    <Page title={t("repForm")} onBack={() => undefined} foot={narrow ? <FootRow>{actions}</FootRow> : undefined}>
      <FormBody>
        <ErrorSummary errors={[{ fieldId: "phone", message: t("badPhone") }]} />
        <FormSection title={t("secClient")}>
          <TextField id="customer" label={t("customer")} required defaultValue="Haddad Lynda" />
          <PhoneField id="phone" label={t("phone")} defaultValue="055 12" error={t("badPhone")} />
        </FormSection>
        <FormSection title={t("secJob")}>
          <TextField id="device" label={t("device")} required defaultValue="iPhone 11" />
          <LongTextField id="problem" label={t("problem")} value={problem} onChange={(event) => setProblem(event.currentTarget.value)} />
          <ChoiceField id="assignee" label={t("assignee")} data={["Rafik", "Yacine"]} />
          <Checkbox id="warranty" label={t("warranty")} />
          <FieldPair>
            <DateField id="received" label={t("received")} required defaultValue="2026-11-01" />
            <DateField id="promised" label={t("promised")} defaultValue="2026-11-04" />
          </FieldPair>
          <FieldPair>
            <MoneyField id="price" label={t("price")} defaultValue={formatNumber(9800, lang === "ar" ? "ar-DZ" : "fr-DZ")} />
            <MoneyField id="parts" label={t("parts")} defaultValue={formatNumber(6200, lang === "ar" ? "ar-DZ" : "fr-DZ")} />
          </FieldPair>
        </FormSection>
        {narrow ? null : <FormActions>{actions}</FormActions>}
      </FormBody>
    </Page>
  );
}

export function FormScreen({ onLocale }: ScreenProps): ReactNode {
  return <RepairFrame current="repairs" onLocale={onLocale} hideNav><FormPage /></RepairFrame>;
}

function RepairCard({ repair }: { repair: Repair }): ReactNode {
  const t = useWords();
  const late = repair.status !== "delivered" && !!repair.promised && repair.promised < TODAY;
  return (
    <BoardCard
      title={<UserText>{repair.device}</UserText>}
      number={<CodeText>{repair.no}</CodeText>}
      subtitle={<UserText>{repair.who}</UserText>}
      meta={repair.promised ? (<><span>{t("promised")} <DateText value={repair.promised} /></span>{late ? <LateTag /> : null}</>) : undefined}
      action={repair.next ? <Button>{t(repair.next)}</Button> : undefined}
      refusal={repair.refused ? { title: t("refusedOf"), reason: t("refused") } : undefined}
    />
  );
}

const STATES: StatusKey[] = ["received", "in_repair", "ready", "delivered"];

function BoardPage({ awkward }: { awkward: boolean }): ReactNode {
  const t = useWords();
  const { say } = useDaftar();
  const { narrow } = useFrame();
  const list = awkward ? awkwardRepairs : repairs;
  const byState = (state: StatusKey): Repair[] => list.filter((repair) => repair.status === state);
  const add = <Button primary fullWidth={narrow} leftSection={<PlusIcon />}>{t("addRep")}</Button>;
  if (narrow) {
    const views = STATES.map((state) => ({ key: state, label: say(statuses[state]), count: byState(state).length }));
    return (
      <Page title={t("navRep")} foot={<FootRow>{add}</FootRow>}>
        <ViewTabs label={t("navRep")} views={views} current="in_repair" />
        {byState("in_repair").map((repair) => <RepairCard key={repair.no} repair={repair} />)}
      </Page>
    );
  }
  return (
    <Page title={t("navRep")} actions={add}>
      <ViewTabs label={t("navRep")} views={[{ key: "board", label: t("boardView") }, { key: "all", label: t("repAll") }]} current="board" />
      <BoardColumns>
        {STATES.map((state) => (
          <BoardColumn key={state} heading={<Status status={state} />} count={byState(state).length}>
            {byState(state).map((repair) => <RepairCard key={repair.no} repair={repair} />)}
          </BoardColumn>
        ))}
      </BoardColumns>
    </Page>
  );
}

export function BoardScreen({ awkward, onLocale }: ScreenProps): ReactNode {
  return <RepairFrame current="repairs" onLocale={onLocale}><BoardPage awkward={awkward} /></RepairFrame>;
}

function RecordPage({ awkward }: { awkward: boolean }): ReactNode {
  const t = useWords();
  const { dir, say } = useDaftar();
  const { narrow } = useFrame();
  const arrow = dir === "rtl" ? "←" : "→";
  const device = awkward ? "Climatiseur mural Condor 12000 BTU Inverter avec télécommande" : "iPhone 11";
  const problem = awkward ? "Écran cassé, batterie gonflée, le client signale aussi que le chargeur chauffe et que l’appareil s’éteint seul après quelques minutes" : "Écran cassé, batterie gonflée";
  const actions = (<><Button primary>{t("mark_ready")}</Button><Button>{t("edit")}</Button></>);
  const { locale } = useDaftar();
  const colon = locale === "fr-DZ" ? "\u00a0:" : ":";
  return (
    <Page title={<UserText>{device}</UserText>} onBack={() => undefined} actions={actions} foot={narrow ? <FootRow>{actions}</FootRow> : undefined}>
      <StateLine><Status status="in_repair" /><CodeText>REP-0234</CodeText></StateLine>
      <TwoColumns>
        <Gutter>
          <FactList>
            <Fact label={t("customer")}><UserText>Haddad Lynda</UserText></Fact>
            <Fact label={t("phone")}><PhoneLink value="0550123456" /></Fact>
            <Fact label={t("problem")}><UserText>{problem}</UserText></Fact>
            <Fact label={t("assignee")}><UserText>Rafik</UserText></Fact>
            <Fact label={t("received")}><DateText value="2026-11-01" /></Fact>
            <Fact label={t("promised")}><DateText value="2026-11-04" /> <LateTag /></Fact>
            <Fact label={t("price")}><Money value={9800} /></Fact>
            <Fact label={t("parts")}><Money value={6200} /></Fact>
            <Fact label={t("margin")}><Money value={3600} /></Fact>
          </FactList>
        </Gutter>
        <Gutter>
          <HistoryList
            title={t("history")}
            entries={[
              { key: "c", meta: <><DateTimeText value="2026-11-05T09:42:00Z" /> · <UserText>Samira</UserText> · {t("srcUi")}</>, changes: <Change label={`${t("price")}${colon}`} from={<Amount value={8500} />} to={<Amount value={9800} />} arrow={arrow} />, action: <TextLink>{t("revert")}</TextLink> },
              { key: "b", meta: <><DateTimeText value="2026-11-03T15:10:00Z" /> · <UserText>Rafik</UserText> · {t("srcFlow")}</>, changes: <Change label={`${t("state")}${colon}`} from={say(statuses.received)} to={say(statuses.in_repair)} arrow={arrow} /> },
              { key: "a", meta: <><DateTimeText value="2026-11-01T08:05:00Z" /> · <UserText>Samira</UserText> · {t("srcUi")}</>, changes: <p>{t("created")}</p> },
            ]}
          />
        </Gutter>
      </TwoColumns>
      <Gutter><LastActions><Button>{t("delete")}</Button></LastActions></Gutter>
    </Page>
  );
}

export function RecordScreen({ awkward, onLocale }: ScreenProps): ReactNode {
  return <RepairFrame current="repairs" onLocale={onLocale} hideNav><RecordPage awkward={awkward} /></RepairFrame>;
}

function CalcPage(): ReactNode {
  const t = useWords();
  const { locale } = useDaftar();
  const { narrow } = useFrame();
  return (
    <Page title={t("navCalc")}>
      <TwoColumns>
        <Gutter>
          <FormBody>
            <FormSection>
              <MoneyField id="subject" label={t("calcSubject")} defaultValue={formatNumber(3000, locale)} />
              <NumberField integer id="subjects" label={t("calcCount")} defaultValue="2" />
              <NumberField integer id="siblings" label={t("calcSiblings")} defaultValue="1" />
              <Button primary type="submit" fullWidth={narrow}>{t("compute")}</Button>
            </FormSection>
          </FormBody>
        </Gutter>
        <Gutter>
          <Statement title={t("result")}>
            <StatementLine label={t("calcRate")}><Percent ratio={0.05} /></StatementLine>
            <StatementLine label={t("calcTotal")} total><Money value={5700} /></StatementLine>
          </Statement>
        </Gutter>
      </TwoColumns>
    </Page>
  );
}

export function CalcScreen(props: ScreenProps): ReactNode {
  return <PayFrame {...props} current="calc"><CalcPage /></PayFrame>;
}

function DashPage({ awkward }: { awkward: boolean }): ReactNode {
  const t = useWords();
  const { locale, say } = useDaftar();
  const { narrow } = useFrame();
  const sum = sumOf(payments);
  const lateRows = payments.filter((row) => row.late);
  const points = awkward
    ? takings.map(([key, value]) => ({ key, label: `${key.slice(8)}/${key.slice(5, 7)}`, value, at: Date.parse(key) }))
    : months.map(([key, value]) => ({ key, label: monthName(Number(key.slice(5)), locale), value }));
  const counts: [StatusKey, number][] = [["paid", 3], ["partial", 3], ["unpaid", 2]];
  return (
    <Page title={t("navCash")}>
      <LeadRow>
        <HeroFigure label={t("kpiDue")} value={formatNumber(sum.rest, locale)} unit={currencyLabel(locale)} note={t("kpiDueNote")} />
        <Statement>
          <StatementLine label={t("kpiLate")}><Money value={sumOf(lateRows).rest} late /></StatementLine>
          <StatementLine label={t("kpiMonth")}><Money value={152300} /></StatementLine>
        </Statement>
      </LeadRow>
      <Panels>
        <Panel title={t("chartPaid")}><LineChart money title={t("chartPaid")} points={points} labelHeading={t("month")} valueHeading={currencyLabel(locale)} /></Panel>
        <Panel title={t("chartState")}><BarList items={counts.map(([key, value]) => ({ key, label: say(statuses[key]), value }))} /></Panel>
        {narrow ? null : (
          <Panel wide title={t("viewLate")}>
            <LedgerTable caption={t("viewLate")} columns={paymentColumns(t, locale, ["status"])} rows={lateRows} rowKey={(row) => row.no} totalLabel={t("total")} totals={totalsOf(lateRows)} />
          </Panel>
        )}
      </Panels>
    </Page>
  );
}

export function DashScreen(props: ScreenProps): ReactNode {
  return <PayFrame {...props} current="cash"><DashPage awkward={props.awkward} /></PayFrame>;
}

export function SetupScreen({ onLocale }: ScreenProps): ReactNode {
  const t = useWords();
  return (
    <AuthLayout firm={t("firmPay")} language={<LanguageSwitch onSwitch={onLocale} />} title={t("setupTitle")} intro={t("setupIntro")}>
      <FormBody>
        <FormSection>
          <TextField id="username" label={t("user")} required autoComplete="username" dir="auto" />
          <PasswordField id="password" label={t("pass")} required autoComplete="new-password" description={t("passHint")} />
          <Button primary fullWidth type="submit">{t("createAccount")}</Button>
        </FormSection>
      </FormBody>
    </AuthLayout>
  );
}

function MenuPage({ onLocale }: { onLocale: (locale: Locale) => void }): ReactNode {
  const t = useWords();
  const { locale } = useDaftar();
  return (
    <Page title={t("firmPay")}>
      <MenuList>
        <MenuHeading>{t("secOther")}</MenuHeading>
        <MenuItem label={t("navCalc")} />
        <MenuHeading>{t("secAccount")}</MenuHeading>
        <MenuItem label={<UserText>Samira</UserText>} value={t("role")} />
        <MenuItem label={t("language")} value={locale === "ar-DZ" ? "العربية" : "Français"} onClick={() => onLocale(locale === "ar-DZ" ? "fr-DZ" : "ar-DZ")} />
        <MenuItem label={t("theme")} value={t("themeAuto")} />
        <MenuItem label={t("logout")} />
      </MenuList>
    </Page>
  );
}

export function MenuScreen(props: ScreenProps): ReactNode {
  return <PayFrame {...props} current="more"><MenuPage onLocale={props.onLocale} /></PayFrame>;
}

function reviewCells(row: number, values: (string | number)[]): SheetCell[] {
  return values.map((value, index) => {
    const ref = `${String.fromCharCode(65 + index)}${row}`;
    const numeric = typeof value === "number";
    const isReste = index === 6;
    return { ref, text: value, numeric, mark: isReste ? (row === 7 ? "flagged" : "evidence") : undefined };
  });
}

const quoted = (lang: string, text: string): ReactNode => (lang === "ar" ? <>«<UserText>{text}</UserText>»</> : <>«{"\u00a0"}<UserText>{text}</UserText>{"\u00a0"}»</>);

export function ReviewScreen({ awkward, onLocale }: ScreenProps): ReactNode {
  const t = useWords();
  const { lang } = useDaftar();
  const q = (text: string): ReactNode => quoted(lang, text);
  const rows = [
    { row: 1, cells: [{ ref: "A1", text: "Paiements janvier 2026", colSpan: 8 }] },
    { row: 2, cells: ["Reçu", "Nom", "Échéance", "Dû", "Payé", "Coût", "Reste", "État"].map((text, index): SheetCell => ({ ref: `${String.fromCharCode(65 + index)}2`, text, mark: "header" })) },
    { row: 3, cells: reviewCells(3, ["R-0101", "Benali Samir", "05/01/2026", 18500, 18500, 9000, 0, "Payé"]) },
    { row: 4, cells: reviewCells(4, ["R-0102", "حورية سعيدي", "05/01/2026", 12000, 5000, 6000, 7000, "Partiel"]) },
    { row: 5, cells: reviewCells(5, ["R-0103", "BENALI Samir", "08/01/2026", 9600, 9600, 4800, 0, "Payé"]) },
    { row: 6, cells: reviewCells(6, ["R-0104", "Meziane Sofiane", "10/01/2026", 24750, 0, 12000, 24750, "Impayé"]) },
    { row: 7, cells: reviewCells(7, ["R-0105", "Haddad Lynda", "12/01/2026", 31200, 15000, 16000, 16200, "Partiel"]) },
    { row: 8, cells: reviewCells(8, ["R-0106", "وليد خليفي", "15/01/2026", 6800, 0, 3000, 6800, "Impayé"]) },
    { row: 9, cells: reviewCells(9, ["R-0107", "Benali S.", "20/01/2026", 4200, 4200, 2000, 0, "Payé"]) },
    { row: 10, cells: (["TOTAL", "", "", 107050, 52300, 52800, 54750, ""] as (string | number)[]).map((value, index): SheetCell => ({ ref: `${String.fromCharCode(65 + index)}10`, text: value, numeric: typeof value === "number", mark: "total" })) },
  ];
  return (
    <BareFrame>
      <ReviewLayout
        file={<bdi dir="ltr">{t("file")}</bdi>}
        actions={<><LanguageSwitch onSwitch={onLocale} /><Button>{t("previewApp")}</Button></>}
        notices={awkward ? <Notice title={t("modelTitle")} actions={<Button>{t("rerun")}</Button>}>{t("modelBody")}</Notice> : undefined}
        tabs={<SheetTabs label={t("file")} tabs={["Janvier", "Février", "مارس", "Clients", "Calcul"]} current="Janvier" />}
        sheet={<SheetGrid label="Janvier" columns={["A", "B", "C", "D", "E", "F", "G", "H"]} rows={rows} />}
        legend={<SheetLegend header={t("lgHeader")} total={t("lgTotal")} evidence={t("lgEvidence")} flagged={t("lgFlagged")} />}
        findings={
          <FindingList count={t("decided")} order={t("lowFirst")} progress={5 / 31} bulkAction={<Button>{t("bulk")}</Button>}>
            <Finding active kind={t("kAnomaly")} level="low" actions={<><Button primary>{t("accept")}</Button><Button>{t("edit")}</Button><Button>{t("reject")}</Button></>}>
              {lang === "ar" ? <>في {q("Reste")}، خلية واحدة لا تتبع صيغة العمود: <CodeText>G7</CodeText>.</> : <>Dans {q("Reste")}, 1 cellule ne suit pas la formule de la colonne{"\u00a0"}: <CodeText>G7</CodeText>.</>}
            </Finding>
            <Finding kind={t("kEntity")} level="medium">
              {lang === "ar" ? <>{q("Nom")} يتكرر في {q("Janvier")}، {q("Février")}، {q("مارس")}: 42 قيمة، منها 3 مكتوبة بعدة طرق (<UserText>Benali Samir / BENALI Samir / Benali S.</UserText>). هل نجعلها قائمة واحدة؟</> : <>{q("Nom")} revient dans {q("Janvier")}, {q("Février")}, {q("مارس")}{"\u00a0"}: 42 valeurs, dont 3 écrites de plusieurs façons (<UserText>Benali Samir / BENALI Samir / Benali S.</UserText>). En faire une seule liste{"\u00a0"}?</>}
            </Finding>
            <Finding kind={t("kChoice")} level="medium">
              {lang === "ar" ? <>{q("État")}: 3 قيم مختلفة فقط (<UserText>Payé, Partiel, Impayé</UserText>). هل نجعلها قائمة اختيارات؟</> : <>{q("État")}{"\u00a0"}: seulement 3 valeurs différentes (Payé, Partiel, Impayé). En faire une liste de choix{"\u00a0"}?</>}
            </Finding>
            <Finding kind={t("kPeriod")} level="high">
              {lang === "ar" ? <>3 أوراق (<UserText>Janvier, Février</UserText>، مارس) لها نفس الأعمدة وعددها 8. هل نجعلها قائمة واحدة مع حقل الشهر؟</> : <>3 feuilles (Janvier, Février, <UserText>مارس</UserText>) ont les mêmes 8 colonnes. En faire une seule liste, avec un champ mois{"\u00a0"}?</>}
            </Finding>
            <Finding kind={t("kTotal")} level="high" state={t("accepted")}>
              {lang === "ar" ? <>الصف 10 في {q("Janvier")} مجموع وليس بيانات: يجمع الصفوف التي فوقه (4 أعمدة).</> : <>La ligne 10 de {q("Janvier")} est un total, pas une donnée{"\u00a0"}: elle additionne les lignes au-dessus (4 colonnes).</>}
            </Finding>
            <Finding kind={t("kComputed")} level="high" state={t("accepted")}>
              {lang === "ar" ? <>{q("Reste")} (<CodeText>remaining</CodeText>) يُحسب بالصيغة <CodeText>=D3-E3</CodeText> في 6 صفوف من 7: سيُعاد حسابه عند كل تعديل.</> : <>{q("Reste")} (remaining) est calculée par la formule <CodeText>=D3-E3</CodeText> sur 6 lignes sur 7{"\u00a0"}: elle sera recalculée à chaque modification.</>}
            </Finding>
          </FindingList>
        }
      />
    </BareFrame>
  );
}

function StudioFrame({ current, onLocale, children }: { current: string; onLocale: (locale: Locale) => void; children: ReactNode }): ReactNode {
  const t = useWords();
  return (
    <AppFrame firm={t("studio")} nav={[[{ key: "projects", label: t("projects") }]]} current={current} language={<LanguageSwitch onSwitch={onLocale} />}>
      {children}
    </AppFrame>
  );
}

function ProjectsPage({ awkward }: { awkward: boolean }): ReactNode {
  const t = useWords();
  const columns: Column<Project>[] = [
    { key: "name", header: t("projectName"), cell: (row) => <TextLink><UserText>{row.name}</UserText></TextLink> },
    { key: "file", header: t("fileName"), cell: (row) => <UserText>{row.file}</UserText> },
    { key: "updated", header: t("updated"), nowrap: true, cell: (row) => <DateText value={row.updated} /> },
    { key: "pending", header: t("pendingCount"), numeric: true, cell: (row) => <Amount value={row.pending} precision={0} /> },
    { key: "decided", header: t("decidedCount"), numeric: true, cell: (row) => <Amount value={row.decided} precision={0} /> },
  ];
  return (
    <Page title={t("projects")}>
      {awkward ? <Notice tone="wrong" title={t("uploadFailed")}>{t("uploadUnreadable")}</Notice> : null}
      <FormBody>
        <FormSection title={t("newProject")}>
          <FileField id="workbook" label={t("workbook")} description={t("workbookHint")} accept=".xlsx,.xlsm,.xls,.ods,.csv" />
        </FormSection>
        <FormActions><Button primary type="submit">{t("analyse")}</Button></FormActions>
      </FormBody>
      {awkward ? null : <Waiting>{t("analysing")} <UserText>Stock_2026.xlsx</UserText></Waiting>}
      <Panels>
        <Panel wide title={t("projectList")}>
          <LedgerTable caption={t("projectList")} columns={columns} rows={awkward ? awkwardProjects : projects} rowKey={(row) => row.id} />
        </Panel>
      </Panels>
    </Page>
  );
}

export function ProjectsScreen({ awkward, onLocale }: ScreenProps): ReactNode {
  return <StudioFrame current="projects" onLocale={onLocale}><ProjectsPage awkward={awkward} /></StudioFrame>;
}

/** What the contract says a person has to see, before moving on to the preview. */
function ReportPage({ awkward }: { awkward: boolean }): ReactNode {
  const t = useWords();
  const seriesColumns: Column<SeriesProblem>[] = [
    { key: "field", header: t("colField"), cell: (row) => <UserText>{row.field}</UserText> },
    { key: "tab", header: t("colTab"), cell: (row) => <UserText>{row.tab}</UserText> },
    { key: "reason", header: t("colReason"), cell: (row) => t(row.reason) },
  ];
  const parityColumns: Column<ParityProblem>[] = [
    { key: "tab", header: t("colTab"), cell: (row) => <UserText>{row.tab}</UserText> },
    { key: "formula", header: t("colFormula"), cell: (row) => <CodeText>{row.formula}</CodeText> },
    { key: "cells", header: t("colCells"), cell: (row) => <CodeText>{row.cells.join(", ")}</CodeText> },
  ];
  const badColumns: Column<BadValue>[] = [
    { key: "tab", header: t("colTab"), cell: (row) => <UserText>{row.tab}</UserText> },
    { key: "cell", header: t("colCell"), nowrap: true, cell: (row) => <CodeText>{row.cell}</CodeText> },
    { key: "field", header: t("colField"), cell: (row) => <UserText>{row.field}</UserText> },
    { key: "expected", header: t("colType"), cell: (row) => t(row.expected) },
  ];
  return (
    <Page title={t("reportTitle")} subtitle={t("reportSummary")} actions={<Button primary>{t("previewApp")}</Button>}>
      {awkward ? <Notice title={t("modelTitle")} actions={<Button>{t("rerun")}</Button>}>{t("modelBody")}</Notice> : null}
      <Notice tone="wrong" title={t("seriesTitle")}>{t("seriesBody")}</Notice>
      <LedgerTable caption={t("seriesTitle")} columns={seriesColumns} rows={awkward ? awkwardSeriesProblems : seriesProblems} rowKey={(row) => `${row.tab}.${row.field}`} />
      <Panels>
        <Panel wide title={t("parityTitle")}>
          <LedgerTable caption={t("parityTitle")} columns={parityColumns} rows={awkward ? awkwardParityProblems : parityProblems} rowKey={(row) => row.tab} />
        </Panel>
        <Panel wide title={t("badValuesTitle")}>
          <LedgerTable caption={t("badValuesTitle")} columns={badColumns} rows={badValues} rowKey={(row) => `${row.tab}.${row.cell}`} />
        </Panel>
        <Panel wide title={t("questionsTitle")}>
          <FormBody>
            <FormSection>
              <NumberField integer id="period-year" label={t("questionYear")} description={t("questionYearHint")} />
            </FormSection>
            <FormActions><Button type="submit">{t("saveAnswer")}</Button></FormActions>
          </FormBody>
        </Panel>
      </Panels>
    </Page>
  );
}

export function ReportScreen({ awkward, onLocale }: ScreenProps): ReactNode {
  return <StudioFrame current="projects" onLocale={onLocale}><ReportPage awkward={awkward} /></StudioFrame>;
}

export const SCREENS = {
  list: { name: "List", component: ListScreen },
  empty: { name: "Empty list", component: EmptyScreen },
  form: { name: "Form with an error", component: FormScreen },
  board: { name: "Board, refused move", component: BoardScreen },
  record: { name: "Record and history", component: RecordScreen },
  calc: { name: "Calculator", component: CalcScreen },
  dash: { name: "Dashboard", component: DashScreen },
  projects: { name: "Projects (Studio)", component: ProjectsScreen },
  review: { name: "Review (Studio)", component: ReviewScreen },
  report: { name: "Report (Studio)", component: ReportScreen },
  setup: { name: "First start", component: SetupScreen },
  menu: { name: "Phone menu", component: MenuScreen },
} as const;

export type ScreenKey = keyof typeof SCREENS;
