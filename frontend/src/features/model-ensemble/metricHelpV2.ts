import { sessionMetricGuidance } from "../quality-profile/metricGuidance";

/**
 * Canonical, versioned presentation registry for the twenty workspace metrics.
 * It is presentation copy only: it never changes a persisted value, never
 * invents transcript-specific evidence, and keeps measured evidence separate
 * from model judgments. English is authoritative; Polish falls back to English
 * per entry when a translation is missing.
 */
export const METRIC_HELP_V2_VERSION = "metric-help-v2.0.0";

export type MetricHelpLocale = "en" | "pl";
export type MetricHelpDirection = "higher_is_better" | "lower_is_better";

export interface MetricHelpEntry {
  /** One sentence: what the metric means. */
  meaning: string;
  /** The question this metric answers. */
  question: string;
  /** What one observation is (the denominator unit). */
  observationUnit: string;
  /** Human-readable direction. */
  direction: string;
  /** What counts toward the numerator. */
  counts: string;
  /** What deliberately does not count. */
  doesNotCount: string;
  /** Objective-evidence requirement (or explicit statement that none makes it proof). */
  objectiveEvidence: string;
}

interface MetricHelpSeed {
  key: string;
  direction: MetricHelpDirection;
  en: MetricHelpEntry;
  pl: MetricHelpEntry;
}

const TEXT_CANDIDATE_EN = "No objective evidence is required for the candidate value; it is a versioned lexical review candidate and never proof of quality or task success.";
const TEXT_CANDIDATE_PL = "Wartość kandydacka nie wymaga obiektywnych dowodów; to wersjonowany leksykalny kandydat do przeglądu, nigdy dowód jakości ani sukcesu zadania.";
const TYPED_EVIDENCE_EN = "Requires a typed local tool, test, artifact, or verification receipt; assistant prose alone stays Unknown.";
const TYPED_EVIDENCE_PL = "Wymaga typowanego lokalnego pokwitowania narzędzia, testu, artefaktu lub weryfikacji; sama proza asystenta pozostaje Nieznana.";
const HIGHER_EN = "Higher is better (radar plots the raw share).";
const HIGHER_PL = "Wyżej znaczy lepiej (radar pokazuje surowy udział).";
const LOWER_EN = "Lower is better (radar plots 100% minus the raw rate).";
const LOWER_PL = "Niżej znaczy lepiej (radar pokazuje 100% minus surowy wskaźnik).";

const SEEDS: readonly MetricHelpSeed[] = [
  {
    key: "prompt.task_definition_coverage", direction: "higher_is_better",
    en: { meaning: "Share of the three task-definition cues (action, target, intended outcome) detected in the focus request.", question: "Did the focus request contain separate action, target, and intended-outcome cues?", observationUnit: "one cue check on the focus request (three per request)", direction: HIGHER_EN, counts: "A detected action, target, or intended-outcome cue in the focus request.", doesNotCount: "Cues in later messages, agent restatements, or implied goals.", objectiveEvidence: TEXT_CANDIDATE_EN },
    pl: { meaning: "Udział trzech sygnałów definicji zadania (działanie, cel, zamierzony rezultat) wykrytych w prośbie głównej.", question: "Czy prośba główna zawierała osobne sygnały działania, celu i zamierzonego rezultatu?", observationUnit: "jedna kontrola sygnału w prośbie głównej (trzy na prośbę)", direction: HIGHER_PL, counts: "Wykryty sygnał działania, celu lub zamierzonego rezultatu w prośbie głównej.", doesNotCount: "Sygnały w późniejszych wiadomościach, parafrazy agenta ani domyślne cele.", objectiveEvidence: TEXT_CANDIDATE_PL },
  },
  {
    key: "prompt.problem_evidence_quality", direction: "higher_is_better",
    en: { meaning: "Share of diagnostic evidence cues (observed, expected, reproduction, environment) present when a bug or diagnosis task is detected.", question: "For a diagnosis task, were observed behavior, expected behavior, reproduction, and environment described?", observationUnit: "one evidence cue check per detected diagnosis request (four per request)", direction: HIGHER_EN, counts: "A described observed behavior, expected behavior, reproduction step, or environment detail.", doesNotCount: "Non-diagnosis tasks (they stay Not applicable) and evidence supplied only by the agent.", objectiveEvidence: TEXT_CANDIDATE_EN },
    pl: { meaning: "Udział sygnałów dowodowych diagnozy (obserwacja, oczekiwanie, reprodukcja, środowisko) obecnych, gdy wykryto zadanie diagnostyczne.", question: "Czy dla zadania diagnostycznego opisano zachowanie obserwowane, oczekiwane, reprodukcję i środowisko?", observationUnit: "jedna kontrola sygnału dowodowego na wykrytą prośbę diagnostyczną (cztery na prośbę)", direction: HIGHER_PL, counts: "Opisane zachowanie obserwowane, oczekiwane, krok reprodukcji lub szczegół środowiska.", doesNotCount: "Zadania niediagnostyczne (pozostają Nie dotyczy) oraz dowody podane wyłącznie przez agenta.", objectiveEvidence: TEXT_CANDIDATE_PL },
  },
  {
    key: "prompt.context_sufficiency", direction: "higher_is_better",
    en: { meaning: "Share of context cues (current state, environment or version, important boundary) present in the focus request.", question: "Did the focus request identify current state, environment or version, and an important boundary?", observationUnit: "one context cue check on the focus request (three per request)", direction: HIGHER_EN, counts: "A current-state fact, an environment or version fact, or an explicit boundary.", doesNotCount: "Context the agent discovered itself or context added after corrections.", objectiveEvidence: TEXT_CANDIDATE_EN },
    pl: { meaning: "Udział sygnałów kontekstu (stan bieżący, środowisko lub wersja, istotna granica) obecnych w prośbie głównej.", question: "Czy prośba główna wskazała stan bieżący, środowisko lub wersję oraz istotną granicę?", observationUnit: "jedna kontrola sygnału kontekstu w prośbie głównej (trzy na prośbę)", direction: HIGHER_PL, counts: "Fakt o stanie bieżącym, fakt o środowisku lub wersji albo jawna granica.", doesNotCount: "Kontekst odkryty samodzielnie przez agenta ani dodany po korektach.", objectiveEvidence: TEXT_CANDIDATE_PL },
  },
  {
    key: "prompt.constraint_precision", direction: "higher_is_better",
    en: { meaning: "Share of detected constraint clauses that carry a concrete boundary, value, platform, version, or prohibition.", question: "How many detected constraints contain a concrete boundary, value, platform, version, or prohibition?", observationUnit: "one detected constraint clause", direction: HIGHER_EN, counts: "A constraint clause with a concrete limit, threshold, platform, version, or prohibition.", doesNotCount: "Absent constraints (they yield Unknown, never zero) and vague wording without a boundary.", objectiveEvidence: TEXT_CANDIDATE_EN },
    pl: { meaning: "Udział wykrytych klauzul ograniczeń zawierających konkretną granicę, wartość, platformę, wersję lub zakaz.", question: "Ile wykrytych ograniczeń zawiera konkretną granicę, wartość, platformę, wersję lub zakaz?", observationUnit: "jedna wykryta klauzula ograniczenia", direction: HIGHER_PL, counts: "Klauzula ograniczenia z konkretnym limitem, progiem, platformą, wersją lub zakazem.", doesNotCount: "Brak ograniczeń (daje Nieznane, nigdy zero) oraz ogólnikowe sformułowania bez granicy.", objectiveEvidence: TEXT_CANDIDATE_PL },
  },
  {
    key: "prompt.acceptance_testability", direction: "higher_is_better",
    en: { meaning: "Share of detected requirements that include an observable pass condition.", question: "How many detected requirements include an observable pass condition?", observationUnit: "one detected requirement clause", direction: HIGHER_EN, counts: "A requirement with a check, threshold, comparison, or explicit pass cue.", doesNotCount: "A test word alone as proof of a complete criterion, or checks the agent invented later.", objectiveEvidence: TEXT_CANDIDATE_EN },
    pl: { meaning: "Udział wykrytych wymagań zawierających obserwowalny warunek zaliczenia.", question: "Ile wykrytych wymagań zawiera obserwowalny warunek zaliczenia?", observationUnit: "jedna wykryta klauzula wymagania", direction: HIGHER_PL, counts: "Wymaganie z sygnałem kontroli, progu, porównania lub jawnego zaliczenia.", doesNotCount: "Samo słowo „test” jako dowód pełnego kryterium ani kontrole wymyślone później przez agenta.", objectiveEvidence: TEXT_CANDIDATE_PL },
  },
  {
    key: "prompt.deliverable_contract", direction: "higher_is_better",
    en: { meaning: "Share of requested deliverables that name a format, interface, location, audience, or compatibility detail.", question: "How many requested deliverables include a format, interface, location, audience, or compatibility detail?", observationUnit: "one detected deliverable clause", direction: HIGHER_EN, counts: "A deliverable clause with at least one concrete output detail.", doesNotCount: "A universal output-slot checklist; only detected deliverables form the denominator.", objectiveEvidence: TEXT_CANDIDATE_EN },
    pl: { meaning: "Udział żądanych rezultatów, które wskazują format, interfejs, lokalizację, odbiorcę lub szczegół zgodności.", question: "Ile żądanych rezultatów zawiera format, interfejs, lokalizację, odbiorcę lub szczegół zgodności?", observationUnit: "jedna wykryta klauzula rezultatu", direction: HIGHER_PL, counts: "Klauzula rezultatu z co najmniej jednym konkretnym szczegółem wyniku.", doesNotCount: "Uniwersalna lista pól wyniku; mianownik tworzą tylko wykryte rezultaty.", objectiveEvidence: TEXT_CANDIDATE_PL },
  },
  {
    key: "collaboration.ambiguity_resolution", direction: "higher_is_better",
    en: { meaning: "Share of detected ambiguity markers that were followed by a related clarification or explicit replacement.", question: "Were detected vague or unresolved references followed by a related clarification?", observationUnit: "one clause with an ambiguity marker", direction: HIGHER_EN, counts: "A later related clarification or explicit replacement of the vague reference.", doesNotCount: "Semantic materiality judgments; markers are review candidates only.", objectiveEvidence: TEXT_CANDIDATE_EN },
    pl: { meaning: "Udział wykrytych znaczników niejednoznaczności, po których nastąpiło powiązane doprecyzowanie lub jawne zastąpienie.", question: "Czy po wykrytych niejasnych odniesieniach nastąpiło powiązane doprecyzowanie?", observationUnit: "jedna klauzula ze znacznikiem niejednoznaczności", direction: HIGHER_PL, counts: "Późniejsze powiązane doprecyzowanie lub jawne zastąpienie niejasnego odniesienia.", doesNotCount: "Ocena istotności semantycznej; znaczniki są tylko kandydatami do przeglądu.", objectiveEvidence: TEXT_CANDIDATE_PL },
  },
  {
    key: "collaboration.clarification_yield", direction: "higher_is_better",
    en: { meaning: "Share of agent questions that received a later related, substantive user answer.", question: "Did agent questions produce a related, substantive user answer?", observationUnit: "one agent question", direction: HIGHER_EN, counts: "A later related user answer carrying concrete task information.", doesNotCount: "Question frequency itself, or answers unrelated to the question.", objectiveEvidence: TEXT_CANDIDATE_EN },
    pl: { meaning: "Udział pytań agenta, na które padła późniejsza powiązana, merytoryczna odpowiedź użytkownika.", question: "Czy pytania agenta przyniosły powiązaną, merytoryczną odpowiedź użytkownika?", observationUnit: "jedno pytanie agenta", direction: HIGHER_PL, counts: "Późniejsza powiązana odpowiedź użytkownika z konkretną informacją o zadaniu.", doesNotCount: "Sama liczba pytań ani odpowiedzi niezwiązane z pytaniem.", objectiveEvidence: TEXT_CANDIDATE_PL },
  },
  {
    key: "collaboration.exploration_conversion", direction: "higher_is_better",
    en: { meaning: "Share of hypothesis or theorizing clauses that later converged into a related plan, decision, action, or verification item.", question: "Did observable hypotheses or theorizing converge into a related plan or evidence step?", observationUnit: "one hypothesis-marker clause", direction: HIGHER_EN, counts: "A later related plan, decision, action, or verification item.", doesNotCount: "An ideal amount of exploration; research tasks need task-type context.", objectiveEvidence: TEXT_CANDIDATE_EN },
    pl: { meaning: "Udział klauzul hipotez lub teoretyzowania, które później przeszły w powiązany plan, decyzję, działanie lub weryfikację.", question: "Czy obserwowalne hipotezy przeszły w powiązany plan lub krok dowodowy?", observationUnit: "jedna klauzula ze znacznikiem hipotezy", direction: HIGHER_PL, counts: "Późniejszy powiązany plan, decyzja, działanie lub element weryfikacji.", doesNotCount: "Idealna ilość eksploracji; zadania badawcze wymagają kontekstu typu zadania.", objectiveEvidence: TEXT_CANDIDATE_PL },
  },
  {
    key: "collaboration.scope_change_discipline", direction: "higher_is_better",
    en: { meaning: "Share of explicit user scope-change clauses that were acknowledged in a related response or revised plan.", question: "Were explicit scope changes acknowledged in a related response or revised plan?", observationUnit: "one explicit user scope-change clause", direction: HIGHER_EN, counts: "A related acknowledgement or revised plan after the change.", doesNotCount: "Intentional iteration as failure; with no change the metric stays Unknown.", objectiveEvidence: TEXT_CANDIDATE_EN },
    pl: { meaning: "Udział jawnych zmian zakresu przez użytkownika potwierdzonych w powiązanej odpowiedzi lub zrewidowanym planie.", question: "Czy jawne zmiany zakresu zostały potwierdzone w powiązanej odpowiedzi lub zrewidowanym planie?", observationUnit: "jedna jawna klauzula zmiany zakresu", direction: HIGHER_PL, counts: "Powiązane potwierdzenie lub zrewidowany plan po zmianie.", doesNotCount: "Zamierzona iteracja jako porażka; bez zmiany metryka pozostaje Nieznana.", objectiveEvidence: TEXT_CANDIDATE_PL },
  },
  {
    key: "collaboration.rework_candidate_rate", direction: "lower_is_better",
    en: { meaning: "Share of user feedback clauses after an agent response that carry correction or misunderstanding markers.", question: "What share of user feedback contains correction or misunderstanding markers?", observationUnit: "one user feedback clause following an agent response", direction: LOWER_EN, counts: "A feedback clause with a correction or misunderstanding marker.", doesNotCount: "New scope or preference changes as rework; every hit is a review candidate.", objectiveEvidence: TEXT_CANDIDATE_EN },
    pl: { meaning: "Udział klauzul opinii użytkownika po odpowiedzi agenta zawierających znaczniki korekty lub nieporozumienia.", question: "Jaki udział opinii użytkownika zawiera znaczniki korekty lub nieporozumienia?", observationUnit: "jedna klauzula opinii użytkownika po odpowiedzi agenta", direction: LOWER_PL, counts: "Klauzula opinii ze znacznikiem korekty lub nieporozumienia.", doesNotCount: "Nowy zakres ani zmiana preferencji jako przeróbka; każde trafienie to kandydat do przeglądu.", objectiveEvidence: TEXT_CANDIDATE_PL },
  },
  {
    key: "logic.decomposition_coverage", direction: "higher_is_better",
    en: { meaning: "Share of detected requirements that could be linked to an explicit plan item.", question: "Could each detected requirement be linked to an explicit plan item?", observationUnit: "one detected requirement", direction: HIGHER_EN, counts: "A conservative lexical link from a requirement to an explicit plan item.", doesNotCount: "Plan adequacy; a link is a candidate, not proof the plan is sufficient.", objectiveEvidence: TEXT_CANDIDATE_EN },
    pl: { meaning: "Udział wykrytych wymagań, które dało się powiązać z jawnym elementem planu.", question: "Czy każde wykryte wymaganie dało się powiązać z jawnym elementem planu?", observationUnit: "jedno wykryte wymaganie", direction: HIGHER_PL, counts: "Ostrożne leksykalne powiązanie wymagania z jawnym elementem planu.", doesNotCount: "Adekwatność planu; powiązanie to kandydat, nie dowód wystarczalności planu.", objectiveEvidence: TEXT_CANDIDATE_PL },
  },
  {
    key: "logic.hypothesis_test_linkage", direction: "higher_is_better",
    en: { meaning: "Share of technical hypotheses followed by a discriminating structured check.", question: "Was each technical hypothesis followed by a discriminating structured check?", observationUnit: "one technical hypothesis", direction: HIGHER_EN, counts: "A typed verification episode that can distinguish the hypothesis from alternatives.", doesNotCount: "Chronological proximity or an agent saying it tested something.", objectiveEvidence: TYPED_EVIDENCE_EN },
    pl: { meaning: "Udział hipotez technicznych, po których nastąpiła rozstrzygająca ustrukturyzowana kontrola.", question: "Czy po każdej hipotezie technicznej nastąpiła rozstrzygająca ustrukturyzowana kontrola?", observationUnit: "jedna hipoteza techniczna", direction: HIGHER_PL, counts: "Typowany epizod weryfikacji zdolny odróżnić hipotezę od alternatyw.", doesNotCount: "Bliskość czasowa ani deklaracja agenta, że coś przetestował.", objectiveEvidence: TYPED_EVIDENCE_PL },
  },
  {
    key: "logic.decision_rationale_coverage", direction: "higher_is_better",
    en: { meaning: "Share of structured decisions connected to a rationale, alternative, constraint, or evidence.", question: "Were observable decisions connected to a rationale, alternative, constraint, or evidence?", observationUnit: "one structured decision item", direction: HIGHER_EN, counts: "A rationale-bearing structured decision item.", doesNotCount: "Free-text decisions; when the projection exposes no decision items the metric abstains.", objectiveEvidence: "Requires structured decision items from the local projection; without them the metric abstains rather than scoring prose." },
    pl: { meaning: "Udział ustrukturyzowanych decyzji powiązanych z uzasadnieniem, alternatywą, ograniczeniem lub dowodem.", question: "Czy obserwowalne decyzje powiązano z uzasadnieniem, alternatywą, ograniczeniem lub dowodem?", observationUnit: "jeden ustrukturyzowany element decyzji", direction: HIGHER_PL, counts: "Ustrukturyzowany element decyzji niosący uzasadnienie.", doesNotCount: "Decyzje w luźnym tekście; bez elementów decyzji w projekcji metryka wstrzymuje ocenę.", objectiveEvidence: "Wymaga ustrukturyzowanych elementów decyzji z lokalnej projekcji; bez nich metryka wstrzymuje ocenę zamiast punktować prozę." },
  },
  {
    key: "logic.requirement_action_traceability", direction: "higher_is_better",
    en: { meaning: "Share of active requirements linked to structured implementation work.", question: "Could every active requirement be linked to structured implementation work?", observationUnit: "one active requirement", direction: HIGHER_EN, counts: "A structured action link (tool, edit, command, or artifact) for the requirement.", doesNotCount: "Generic agent response text reclassified as an action.", objectiveEvidence: TYPED_EVIDENCE_EN },
    pl: { meaning: "Udział aktywnych wymagań powiązanych z ustrukturyzowaną pracą implementacyjną.", question: "Czy każde aktywne wymaganie dało się powiązać z ustrukturyzowaną pracą implementacyjną?", observationUnit: "jedno aktywne wymaganie", direction: HIGHER_PL, counts: "Ustrukturyzowane powiązanie działania (narzędzie, edycja, polecenie lub artefakt) z wymaganiem.", doesNotCount: "Ogólny tekst odpowiedzi agenta przeklasyfikowany na działanie.", objectiveEvidence: TYPED_EVIDENCE_PL },
  },
  {
    key: "logic.open_loop_closure", direction: "higher_is_better",
    en: { meaning: "Share of detected questions followed by a related opposite-role response and not reopened.", question: "Were detected questions followed by a related opposite-role response and not reopened?", observationUnit: "one detected question", direction: HIGHER_EN, counts: "A related closing response from the other role that is not reopened later.", doesNotCount: "Answer correctness; a linked response is not proof the answer is right.", objectiveEvidence: TEXT_CANDIDATE_EN },
    pl: { meaning: "Udział wykrytych pytań, po których nastąpiła powiązana odpowiedź drugiej strony bez ponownego otwarcia.", question: "Czy po wykrytych pytaniach nastąpiła powiązana odpowiedź drugiej strony bez ponownego otwarcia?", observationUnit: "jedno wykryte pytanie", direction: HIGHER_PL, counts: "Powiązana zamykająca odpowiedź drugiej roli, nieotwarta ponownie później.", doesNotCount: "Poprawność odpowiedzi; powiązana odpowiedź nie dowodzi, że jest właściwa.", objectiveEvidence: TEXT_CANDIDATE_PL },
  },
  {
    key: "outcome.agent_claim_grounding", direction: "higher_is_better",
    en: { meaning: "Share of material completion or correctness claims backed by objective evidence.", question: "Are material completion claims backed by objective evidence?", observationUnit: "one material agent claim", direction: HIGHER_EN, counts: "A claim linked to typed tool, test, source, or artifact evidence.", doesNotCount: "An assistant completion claim on its own; it is never proof of delivery.", objectiveEvidence: TYPED_EVIDENCE_EN },
    pl: { meaning: "Udział istotnych deklaracji ukończenia lub poprawności popartych obiektywnymi dowodami.", question: "Czy istotne deklaracje ukończenia są poparte obiektywnymi dowodami?", observationUnit: "jedna istotna deklaracja agenta", direction: HIGHER_PL, counts: "Deklaracja powiązana z typowanym dowodem z narzędzia, testu, źródła lub artefaktu.", doesNotCount: "Sama deklaracja ukończenia przez asystenta; nigdy nie jest dowodem dostarczenia.", objectiveEvidence: TYPED_EVIDENCE_PL },
  },
  {
    key: "outcome.verification_strategy_adequacy", direction: "higher_is_better",
    en: { meaning: "Share of detected requirements that received a related planned check.", question: "Did each detected requirement receive a related planned check?", observationUnit: "one detected requirement", direction: HIGHER_EN, counts: "A later plan or response with a check cue linked to the requirement.", doesNotCount: "Whether the check ran or passed; this is stated strategy only.", objectiveEvidence: "No execution evidence is required for the stated strategy; run and pass evidence belongs to first-pass and verified-coverage metrics." },
    pl: { meaning: "Udział wykrytych wymagań, dla których zaplanowano powiązaną kontrolę.", question: "Czy każde wykryte wymaganie otrzymało powiązaną zaplanowaną kontrolę?", observationUnit: "jedno wykryte wymaganie", direction: HIGHER_PL, counts: "Późniejszy plan lub odpowiedź z sygnałem kontroli powiązanym z wymaganiem.", doesNotCount: "Czy kontrola się wykonała lub przeszła; to tylko deklarowana strategia.", objectiveEvidence: "Deklarowana strategia nie wymaga dowodów wykonania; dowody uruchomienia i zaliczenia należą do metryk pierwszego przebiegu i pokrycia zweryfikowanego." },
  },
  {
    key: "outcome.first_pass_verification", direction: "higher_is_better",
    en: { meaning: "Whether the first meaningful executable verification episode passed.", question: "Did the first meaningful executable verification episode pass?", observationUnit: "one eligible task with an ordered verification episode", direction: HIGHER_EN, counts: "A first meaningful typed verification episode with a passing outcome.", doesNotCount: "Retries (they cannot improve it) and missing checks (they never become failure).", objectiveEvidence: TYPED_EVIDENCE_EN },
    pl: { meaning: "Czy pierwszy istotny wykonywalny epizod weryfikacji zakończył się powodzeniem.", question: "Czy pierwszy istotny wykonywalny epizod weryfikacji przeszedł?", observationUnit: "jedno kwalifikujące się zadanie z uporządkowanym epizodem weryfikacji", direction: HIGHER_PL, counts: "Pierwszy istotny typowany epizod weryfikacji z wynikiem pozytywnym.", doesNotCount: "Ponowienia (nie poprawiają wyniku) ani brak kontroli (nigdy nie staje się porażką).", objectiveEvidence: TYPED_EVIDENCE_PL },
  },
  {
    key: "outcome.verified_requirement_coverage", direction: "higher_is_better",
    en: { meaning: "Share of active requirements with objective passing evidence or explicit acceptance.", question: "How many active requirements have objective passing evidence or explicit acceptance?", observationUnit: "one active requirement", direction: HIGHER_EN, counts: "A typed requirement-to-verification link with a pass, or explicit human acceptance.", doesNotCount: "Completion claims, unrelated green checks, or deferred requirements.", objectiveEvidence: TYPED_EVIDENCE_EN },
    pl: { meaning: "Udział aktywnych wymagań z obiektywnym dowodem zaliczenia lub jawną akceptacją.", question: "Ile aktywnych wymagań ma obiektywny dowód zaliczenia lub jawną akceptację?", observationUnit: "jedno aktywne wymaganie", direction: HIGHER_PL, counts: "Typowane powiązanie wymagania z weryfikacją zakończoną zaliczeniem lub jawna akceptacja człowieka.", doesNotCount: "Deklaracje ukończenia, niezwiązane zielone kontrole ani odroczone wymagania.", objectiveEvidence: TYPED_EVIDENCE_PL },
  },
];

export const METRIC_HELP_V2_KEYS: readonly string[] = SEEDS.map((seed) => seed.key);

export const METRIC_HELP_V2: Readonly<Record<MetricHelpLocale, Readonly<Record<string, MetricHelpEntry>>>> = {
  en: Object.fromEntries(SEEDS.map((seed) => [seed.key, seed.en])),
  pl: Object.fromEntries(SEEDS.map((seed) => [seed.key, seed.pl])),
};

export const METRIC_HELP_V2_DIRECTIONS: Readonly<Record<string, MetricHelpDirection>> =
  Object.fromEntries(SEEDS.map((seed) => [seed.key, seed.direction]));

export interface ResolvedMetricHelp {
  version: typeof METRIC_HELP_V2_VERSION;
  metricKey: string;
  requestedLocale: MetricHelpLocale;
  locale: MetricHelpLocale;
  fallback: boolean;
  entry: MetricHelpEntry;
}

/** Resolve help for one metric; unknown or partial locales fall back to English. */
export function metricHelpV2(metricKey: string, locale: MetricHelpLocale = "en"): ResolvedMetricHelp | null {
  const requested = METRIC_HELP_V2[locale] as Readonly<Record<string, MetricHelpEntry>> | undefined;
  const english = METRIC_HELP_V2.en[metricKey];
  if (english === undefined) return null;
  const entry = requested?.[metricKey];
  if (entry === undefined || locale === "en") {
    return { version: METRIC_HELP_V2_VERSION, metricKey, requestedLocale: locale, locale: "en", fallback: locale !== "en", entry: english };
  }
  return { version: METRIC_HELP_V2_VERSION, metricKey, requestedLocale: locale, locale, fallback: false, entry };
}

export type MetricInspectorKind =
  | "pending"
  | "not_applicable"
  | "unknown"
  | "abstained"
  | "execution_error"
  | "missing"
  | "experimental"
  | "zero"
  | "measured"
  | "strong";

export interface MetricInspectorInput {
  metricKey: string;
  label: string;
  state: "known" | "unknown" | "not_applicable" | "abstained" | "execution_error" | "missing";
  direction: MetricHelpDirection;
  numericValue: number | null;
  numerator: number | null;
  denominator: number | null;
  explanationCode?: string | null;
  /** Factor keys taken only from a loaded, receipt-backed factor distribution. */
  measuredFactorKeys?: readonly string[];
  /** True when an experimental estimate is visible for this metric. */
  experimentalVisible?: boolean;
  /** True when an estimate exists but is withheld. */
  experimentalWithheld?: boolean;
  /** Radar-quality median of a visible estimate (0..1). */
  experimentalMedian?: number | null;
}

export interface MetricInspectorSentences {
  kind: MetricInspectorKind;
  /** State- or factor-grounded diagnosis. */
  diagnosis: string;
  /** One action plus how to verify it. */
  action: string;
  audience: string;
  basis: string;
}

function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function lowerFirst(value: string): string {
  return value.charAt(0).toLowerCase() + value.slice(1);
}

function readableFactor(value: string): string {
  return value.replaceAll("_", " ").replaceAll(".", " ");
}

function inspectorKind(input: MetricInspectorInput): MetricInspectorKind {
  if (input.state !== "known" && input.explanationCode === "episode_horizon_open") return "pending";
  if (input.state === "not_applicable") return "not_applicable";
  if (input.state === "execution_error") return "execution_error";
  if (input.state === "abstained") return "abstained";
  if (input.state === "missing") return input.experimentalVisible ? "experimental" : "missing";
  if (input.state === "unknown") return input.experimentalVisible ? "experimental" : "unknown";
  if (input.numericValue === null) return input.experimentalVisible ? "experimental" : "unknown";
  if (input.numericValue === 0 && input.direction === "higher_is_better") return "zero";
  const oriented = input.direction === "lower_is_better" ? 1 - input.numericValue : input.numericValue;
  return oriented >= 0.75 ? "strong" : "measured";
}

/**
 * Two deterministic sentences for the selected-metric inspector. Factor keys are
 * mentioned only when the caller passes measured, receipt-backed factor keys.
 */
export function metricInspectorSentences(input: MetricInspectorInput): MetricInspectorSentences {
  const help = metricHelpV2(input.metricKey, "en")?.entry;
  const unit = help?.observationUnit ?? "observation";
  const evidence = help?.objectiveEvidence ?? "Objective evidence outranks prose.";
  const kind = inspectorKind(input);
  const guidance = sessionMetricGuidance(input.metricKey, {
    state: input.state,
    numericValue: input.numericValue,
    direction: input.direction,
    explanationCode: input.explanationCode ?? null,
    factorKeys: input.measuredFactorKeys ?? [],
    experimentalOnly: kind === "experimental",
  });
  const action = `${guidance.action.replace(/[.\s]+$/u, "")} — verify: ${lowerFirst(guidance.verification)}`;
  const fraction = input.numerator !== null && input.denominator !== null
    ? `${input.numerator}/${input.denominator} (${unit})`
    : `an unexposed fraction of ${unit}`;
  const factors = (input.measuredFactorKeys ?? []).slice(0, 2).map(readableFactor);
  let diagnosis: string;
  switch (kind) {
    case "pending":
      diagnosis = `Pending: the newest episode is still open, so ${input.label} cannot be judged yet; this is open evidence, not a zero and not a measurement.`;
      break;
    case "not_applicable":
      diagnosis = `Not applicable: no eligible ${unit} was observed in this window, so there is nothing to score and no value is implied.`;
      break;
    case "unknown":
      diagnosis = `Unknown: the evidence required for ${input.label} is unavailable in this sealed receipt (${lowerFirst(evidence)}) — this is missing evidence, not a low value.`;
      break;
    case "abstained":
      diagnosis = `Needs evidence: the local contract could not establish a defensible denominator of ${unit} for ${input.label}, so it abstained instead of guessing.`;
      break;
    case "execution_error":
      diagnosis = `Error: the local analysis stage for ${input.label} failed before producing a value; the last valid receipt stands and this is not a low score.`;
      break;
    case "missing":
      diagnosis = `No record: ${input.label} is not present in this sealed receipt, so nothing was measured or estimated for it.`;
      break;
    case "experimental":
      diagnosis = `Experimental only: ${input.label} has no measured value; the visible ${input.experimentalMedian == null ? "estimate" : `${percent(input.experimentalMedian)} radar-quality estimate`} is an uncalibrated model range, not a measurement or a probability of success.`;
      break;
    case "zero":
      diagnosis = `Proven zero: ${fraction} met the versioned local contract for ${input.label}; this is a real measured negative that sits at the radar center, not missing data.`;
      break;
    case "strong": {
      const oriented = input.direction === "lower_is_better" ? 1 - input.numericValue! : input.numericValue!;
      diagnosis = input.direction === "lower_is_better"
        ? `Measured: ${fraction} carried the lower-is-better marker (raw ${percent(input.numericValue!)}), so radar quality is ${percent(oriented)}, in the strong band; still a versioned local candidate, not a calibrated quality score.`
        : `Measured: ${fraction} met the versioned local contract for ${input.label} (${percent(oriented)}), in the strong band; still a versioned local candidate, not a calibrated quality score.`;
      break;
    }
    case "measured":
    default: {
      const oriented = input.direction === "lower_is_better" ? 1 - input.numericValue! : input.numericValue!;
      const grounding = factors.length > 0
        ? ` The receipt-backed factor distribution is weakest on ${factors.join(" and ")}.`
        : input.experimentalWithheld
          ? " No factor evidence is shown because the experimental estimate is withheld."
          : "";
      diagnosis = input.direction === "lower_is_better"
        ? `Measured: ${fraction} carried the lower-is-better marker (raw ${percent(input.numericValue!)}), so radar quality is ${percent(oriented)}, below the 75% strong band.${grounding}`
        : `Measured: ${fraction} met the versioned local contract for ${input.label} (${percent(oriented)}), below the 75% strong band.${grounding}`;
      break;
    }
  }
  return { kind, diagnosis, action, audience: guidance.audience, basis: guidance.basis };
}
