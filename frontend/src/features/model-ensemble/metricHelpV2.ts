import { metricDecisionGuidance, sessionMetricGuidance } from "../quality-profile/metricGuidance";
import { QUALITY_ANALYSIS_DEFINITIONS } from "../quality-profile/qualityProfile";

/**
 * Canonical, versioned presentation registry for the twenty workspace metrics.
 *
 * Two layers are kept visibly separate:
 * - `entry` explains the CURRENT local candidate definition whose legacy
 *   receipt is rendered by this workspace.
 * - `measurement` is bound to the SHIPPED measurement source: the versioned
 *   coaching definitions whose receipts this UI actually displays today. The
 *   backend V2 publication contract is not integrated in this UI, so nothing
 *   here describes it as implemented.
 *
 * Presentation copy only: it never changes a persisted value, never invents
 * transcript-specific evidence, and keeps measured evidence separate from model
 * judgments. English is the only shipped UI locale; Polish entries are kept in
 * the registry for a future locale signal and are not surfaced by any UI path.
 */
export const METRIC_HELP_V2_VERSION = "metric-help-v2.1.0";
export const METRIC_HELP_V2_SHIPPED_LOCALES = ["en"] as const;

export type MetricHelpLocale = "en" | "pl";
export type MetricHelpDirection = "higher_is_better" | "lower_is_better";

export interface MetricHelpEntry {
  /** One sentence: what the current local candidate definition measures. */
  meaning: string;
  question: string;
  observationUnit: string;
  direction: string;
  counts: string;
  doesNotCount: string;
  /** Objective-evidence requirement, or an explicit statement that the value is a candidate, not proof. */
  objectiveEvidence: string;
}

export interface MetricHelpMeasurement {
  /** Version of the shipped coaching definition whose receipts are displayed. */
  definitionVersion: number;
  method: string;
  limitation: string;
  /** True when a typed/objective receipt is required and prose abstains. */
  objective: boolean;
}

interface MetricHelpSeed {
  key: string;
  direction: MetricHelpDirection;
  objective: boolean;
  en: MetricHelpEntry;
  pl: MetricHelpEntry;
}

const TEXT_CANDIDATE_EN = "No objective receipt backs the candidate value; it is a versioned lexical review candidate and never proof of quality or task success.";
const TEXT_CANDIDATE_PL = "Wartości kandydackiej nie potwierdza żadne obiektywne pokwitowanie; to wersjonowany leksykalny kandydat do przeglądu, nigdy dowód jakości ani sukcesu zadania.";
const TYPED_EVIDENCE_EN = "Requires a typed local tool, test, artifact, or verification receipt; without one the metric abstains and assistant prose is never counted.";
const TYPED_EVIDENCE_PL = "Wymaga typowanego lokalnego pokwitowania narzędzia, testu, artefaktu lub weryfikacji; bez niego metryka wstrzymuje ocenę, a proza asystenta nigdy nie jest liczona.";
const HIGHER_EN = "Higher is better (radar plots the raw share).";
const HIGHER_PL = "Wyżej znaczy lepiej (radar pokazuje surowy udział).";
const LOWER_EN = "Lower is better (radar plots 100% minus the raw rate; the center is a raw rate of 100%).";
const LOWER_PL = "Niżej znaczy lepiej (radar pokazuje 100% minus surowy wskaźnik; środek oznacza surowy wskaźnik 100%).";

const SEEDS: readonly MetricHelpSeed[] = [
  {
    key: "prompt.task_definition_coverage", direction: "higher_is_better", objective: false,
    en: { meaning: "Share of the three task-definition cues (action, target, intended outcome) detected in the focus request.", question: "Did the focus request contain separate action, target, and intended-outcome cues?", observationUnit: "one cue check on the focus request (three per request)", direction: HIGHER_EN, counts: "A detected action, target, or intended-outcome cue in the focus request.", doesNotCount: "Cues in later messages, agent restatements, or implied goals.", objectiveEvidence: TEXT_CANDIDATE_EN },
    pl: { meaning: "Udział trzech sygnałów definicji zadania (działanie, cel, zamierzony rezultat) wykrytych w prośbie głównej.", question: "Czy prośba główna zawierała osobne sygnały działania, celu i zamierzonego rezultatu?", observationUnit: "jedna kontrola sygnału w prośbie głównej (trzy na prośbę)", direction: HIGHER_PL, counts: "Wykryty sygnał działania, celu lub zamierzonego rezultatu w prośbie głównej.", doesNotCount: "Sygnały w późniejszych wiadomościach, parafrazy agenta ani domyślne cele.", objectiveEvidence: TEXT_CANDIDATE_PL },
  },
  {
    key: "prompt.problem_evidence_quality", direction: "higher_is_better", objective: false,
    en: { meaning: "Share of four legacy diagnostic cue checks (observed/diagnostic wording, expected, reproduction, environment) present when a bug or diagnosis candidate is detected.", question: "For a detected diagnosis request, which of the four legacy cue checks fired?", observationUnit: "one legacy evidence-cue check per detected diagnosis request (four per request)", direction: HIGHER_EN, counts: "Observed wording or any diagnostic keyword satisfies the shipped observed check; expected wording, reproduction wording, and environment details satisfy the other checks.", doesNotCount: "Requests without a detected diagnosis candidate: they stay Unknown, never zero. A fired cue is not proof that the evidence is complete or correct.", objectiveEvidence: TEXT_CANDIDATE_EN },
    pl: { meaning: "Udział czterech starszych kontroli sygnałów diagnozy (sformułowanie obserwacji lub diagnozy, oczekiwanie, reprodukcja, środowisko), gdy wykryto kandydata diagnozy.", question: "Które z czterech starszych kontroli sygnałów zadziałały dla wykrytej prośby diagnostycznej?", observationUnit: "jedna starsza kontrola sygnału na wykrytą prośbę diagnostyczną (cztery na prośbę)", direction: HIGHER_PL, counts: "Sformułowanie obserwacji lub dowolne słowo diagnostyczne spełnia dostarczaną kontrolę obserwacji; osobne kontrole dotyczą oczekiwań, reprodukcji i środowiska.", doesNotCount: "Prośby bez wykrytego kandydata diagnozy: pozostają Nieznane, nigdy zero. Zadziałanie sygnału nie dowodzi kompletności ani poprawności dowodu.", objectiveEvidence: TEXT_CANDIDATE_PL },
  },
  {
    key: "prompt.context_sufficiency", direction: "higher_is_better", objective: false,
    en: { meaning: "Share of context cues (current state, environment or version, important boundary) present in the focus request.", question: "Did the focus request identify current state, environment or version, and an important boundary?", observationUnit: "one context cue check on the focus request (three per request)", direction: HIGHER_EN, counts: "A current-state fact, an environment or version fact, or an explicit boundary.", doesNotCount: "Context the agent discovered itself or context added after corrections.", objectiveEvidence: TEXT_CANDIDATE_EN },
    pl: { meaning: "Udział sygnałów kontekstu (stan bieżący, środowisko lub wersja, istotna granica) obecnych w prośbie głównej.", question: "Czy prośba główna wskazała stan bieżący, środowisko lub wersję oraz istotną granicę?", observationUnit: "jedna kontrola sygnału kontekstu w prośbie głównej (trzy na prośbę)", direction: HIGHER_PL, counts: "Fakt o stanie bieżącym, fakt o środowisku lub wersji albo jawna granica.", doesNotCount: "Kontekst odkryty samodzielnie przez agenta ani dodany po korektach.", objectiveEvidence: TEXT_CANDIDATE_PL },
  },
  {
    key: "prompt.constraint_precision", direction: "higher_is_better", objective: false,
    en: { meaning: "Share of detected constraint clauses that also match the shipped concrete-detail vocabulary or a numeric bound.", question: "How many detected constraints include a recognized platform, version, numeric threshold, unit, or concrete environment term?", observationUnit: "one detected constraint clause", direction: HIGHER_EN, counts: "A constraint clause with a recognized numeric limit, threshold, platform, version, unit, or concrete environment term.", doesNotCount: "Absent constraints (they yield Unknown, never zero), vague wording, and a generic prohibition such as 'must not write files' without another recognized concrete detail.", objectiveEvidence: TEXT_CANDIDATE_EN },
    pl: { meaning: "Udział wykrytych klauzul ograniczeń, które pasują też do dostarczanego słownika konkretów lub granicy liczbowej.", question: "Ile wykrytych ograniczeń zawiera rozpoznaną platformę, wersję, próg liczbowy, jednostkę lub konkretny termin środowiska?", observationUnit: "jedna wykryta klauzula ograniczenia", direction: HIGHER_PL, counts: "Klauzula ograniczenia z rozpoznanym limitem liczbowym, progiem, platformą, wersją, jednostką lub konkretnym terminem środowiska.", doesNotCount: "Brak ograniczeń (daje Nieznane, nigdy zero), ogólniki oraz sam ogólny zakaz bez innego rozpoznanego konkretu.", objectiveEvidence: TEXT_CANDIDATE_PL },
  },
  {
    key: "prompt.acceptance_testability", direction: "higher_is_better", objective: false,
    en: { meaning: "Share of detected requirements that carry an observable pass-condition cue.", question: "How many detected requirements include an observable pass condition?", observationUnit: "one detected requirement clause", direction: HIGHER_EN, counts: "A requirement clause with a check, test, threshold, comparison, or explicit pass cue; a bare test word can satisfy the shipped legacy heuristic.", doesNotCount: "The cue is not proof of a complete or correct acceptance criterion; checks the agent added later are not counted.", objectiveEvidence: TEXT_CANDIDATE_EN },
    pl: { meaning: "Udział wykrytych wymagań niosących sygnał obserwowalnego warunku zaliczenia.", question: "Ile wykrytych wymagań zawiera obserwowalny warunek zaliczenia?", observationUnit: "jedna wykryta klauzula wymagania", direction: HIGHER_PL, counts: "Klauzula wymagania z sygnałem kontroli, testu, progu, porównania lub jawnego zaliczenia; samo słowo „test” może spełnić dostarczaną heurystykę.", doesNotCount: "Sygnał nie dowodzi pełnego ani poprawnego kryterium akceptacji; kontrole dodane później przez agenta nie są liczone.", objectiveEvidence: TEXT_CANDIDATE_PL },
  },
  {
    key: "prompt.deliverable_contract", direction: "higher_is_better", objective: false,
    en: { meaning: "Share of detected deliverable clauses that also match the shipped format, interface, audience, compatibility, or platform-detail vocabulary.", question: "How many detected deliverables include a recognized format, interface, audience, compatibility, or platform detail?", observationUnit: "one detected deliverable clause", direction: HIGHER_EN, counts: "A deliverable clause with a recognized format, interface, audience, compatibility, or platform token.", doesNotCount: "A path or location alone is not recognized by the shipped detail heuristic; only detected deliverable clauses form the denominator.", objectiveEvidence: TEXT_CANDIDATE_EN },
    pl: { meaning: "Udział wykrytych klauzul rezultatu, które pasują też do dostarczanego słownika formatu, interfejsu, odbiorcy, zgodności lub platformy.", question: "Ile wykrytych rezultatów zawiera rozpoznany format, interfejs, odbiorcę, zgodność lub szczegół platformy?", observationUnit: "jedna wykryta klauzula rezultatu", direction: HIGHER_PL, counts: "Klauzula rezultatu z rozpoznanym tokenem formatu, interfejsu, odbiorcy, zgodności lub platformy.", doesNotCount: "Sama ścieżka lub lokalizacja nie jest rozpoznawana przez dostarczaną heurystykę szczegółu; mianownik tworzą tylko wykryte rezultaty.", objectiveEvidence: TEXT_CANDIDATE_PL },
  },
  {
    key: "collaboration.ambiguity_resolution", direction: "higher_is_better", objective: false,
    en: { meaning: "Share of detected ambiguity markers that were followed by a related clarification or explicit replacement.", question: "Were detected vague or unresolved references followed by a related clarification?", observationUnit: "one clause with an ambiguity marker", direction: HIGHER_EN, counts: "A later related clarification or explicit replacement of the vague reference.", doesNotCount: "Semantic materiality judgments; markers are review candidates only.", objectiveEvidence: TEXT_CANDIDATE_EN },
    pl: { meaning: "Udział wykrytych znaczników niejednoznaczności, po których nastąpiło powiązane doprecyzowanie lub jawne zastąpienie.", question: "Czy po wykrytych niejasnych odniesieniach nastąpiło powiązane doprecyzowanie?", observationUnit: "jedna klauzula ze znacznikiem niejednoznaczności", direction: HIGHER_PL, counts: "Późniejsze powiązane doprecyzowanie lub jawne zastąpienie niejasnego odniesienia.", doesNotCount: "Ocena istotności semantycznej; znaczniki są tylko kandydatami do przeglądu.", objectiveEvidence: TEXT_CANDIDATE_PL },
  },
  {
    key: "collaboration.clarification_yield", direction: "higher_is_better", objective: false,
    en: { meaning: "Share of agent questions that received a later related, substantive user answer.", question: "Did agent questions produce a related, substantive user answer?", observationUnit: "one agent question", direction: HIGHER_EN, counts: "A later related user answer carrying concrete task information.", doesNotCount: "Question frequency itself, or answers unrelated to the question.", objectiveEvidence: TEXT_CANDIDATE_EN },
    pl: { meaning: "Udział pytań agenta, na które padła późniejsza powiązana, merytoryczna odpowiedź użytkownika.", question: "Czy pytania agenta przyniosły powiązaną, merytoryczną odpowiedź użytkownika?", observationUnit: "jedno pytanie agenta", direction: HIGHER_PL, counts: "Późniejsza powiązana odpowiedź użytkownika z konkretną informacją o zadaniu.", doesNotCount: "Sama liczba pytań ani odpowiedzi niezwiązane z pytaniem.", objectiveEvidence: TEXT_CANDIDATE_PL },
  },
  {
    key: "collaboration.exploration_conversion", direction: "higher_is_better", objective: false,
    en: { meaning: "Share of hypothesis or theorizing clauses that later converged into a related plan, decision, action, or verification item.", question: "Did observable hypotheses or theorizing converge into a related plan or evidence step?", observationUnit: "one hypothesis-marker clause", direction: HIGHER_EN, counts: "A later related plan, decision, action, or verification item.", doesNotCount: "An ideal amount of exploration; research tasks need task-type context.", objectiveEvidence: TEXT_CANDIDATE_EN },
    pl: { meaning: "Udział klauzul hipotez lub teoretyzowania, które później przeszły w powiązany plan, decyzję, działanie lub weryfikację.", question: "Czy obserwowalne hipotezy przeszły w powiązany plan lub krok dowodowy?", observationUnit: "jedna klauzula ze znacznikiem hipotezy", direction: HIGHER_PL, counts: "Późniejszy powiązany plan, decyzja, działanie lub element weryfikacji.", doesNotCount: "Idealna ilość eksploracji; zadania badawcze wymagają kontekstu typu zadania.", objectiveEvidence: TEXT_CANDIDATE_PL },
  },
  {
    key: "collaboration.scope_change_discipline", direction: "higher_is_better", objective: false,
    en: { meaning: "Share of explicit user scope-change clauses that were acknowledged in a related response or revised plan.", question: "Were explicit scope changes acknowledged in a related response or revised plan?", observationUnit: "one explicit user scope-change clause", direction: HIGHER_EN, counts: "A related acknowledgement or revised plan after the change.", doesNotCount: "Intentional iteration as failure; with no change the metric stays Unknown.", objectiveEvidence: TEXT_CANDIDATE_EN },
    pl: { meaning: "Udział jawnych zmian zakresu przez użytkownika potwierdzonych w powiązanej odpowiedzi lub zrewidowanym planie.", question: "Czy jawne zmiany zakresu zostały potwierdzone w powiązanej odpowiedzi lub zrewidowanym planie?", observationUnit: "jedna jawna klauzula zmiany zakresu", direction: HIGHER_PL, counts: "Powiązane potwierdzenie lub zrewidowany plan po zmianie.", doesNotCount: "Zamierzona iteracja jako porażka; bez zmiany metryka pozostaje Nieznana.", objectiveEvidence: TEXT_CANDIDATE_PL },
  },
  {
    key: "collaboration.rework_candidate_rate", direction: "lower_is_better", objective: false,
    en: { meaning: "Share of user feedback clauses after an agent response that carry correction or misunderstanding markers.", question: "What share of user feedback contains correction or misunderstanding markers?", observationUnit: "one user feedback clause following an agent response", direction: LOWER_EN, counts: "Any feedback clause with a correction or misunderstanding marker — the shipped heuristic also catches some new-scope, preference, and healthy-iteration clauses.", doesNotCount: "Nothing is proven rework: the rule cannot separate genuine rework from new information, so every hit is a review candidate.", objectiveEvidence: TEXT_CANDIDATE_EN },
    pl: { meaning: "Udział klauzul opinii użytkownika po odpowiedzi agenta zawierających znaczniki korekty lub nieporozumienia.", question: "Jaki udział opinii użytkownika zawiera znaczniki korekty lub nieporozumienia?", observationUnit: "jedna klauzula opinii użytkownika po odpowiedzi agenta", direction: LOWER_PL, counts: "Każda klauzula opinii ze znacznikiem korekty lub nieporozumienia — dostarczana heurystyka łapie też część klauzul nowego zakresu, preferencji i zdrowej iteracji.", doesNotCount: "Nic nie jest dowiedzioną przeróbką: reguła nie odróżnia prawdziwej przeróbki od nowej informacji, więc każde trafienie to kandydat do przeglądu.", objectiveEvidence: TEXT_CANDIDATE_PL },
  },
  {
    key: "logic.decomposition_coverage", direction: "higher_is_better", objective: false,
    en: { meaning: "Share of detected requirements that could be linked to an explicit plan item.", question: "Could each detected requirement be linked to an explicit plan item?", observationUnit: "one detected requirement", direction: HIGHER_EN, counts: "A conservative lexical link from a requirement to an explicit plan item.", doesNotCount: "Plan adequacy; a link is a candidate, not proof the plan is sufficient.", objectiveEvidence: TEXT_CANDIDATE_EN },
    pl: { meaning: "Udział wykrytych wymagań, które dało się powiązać z jawnym elementem planu.", question: "Czy każde wykryte wymaganie dało się powiązać z jawnym elementem planu?", observationUnit: "jedno wykryte wymaganie", direction: HIGHER_PL, counts: "Ostrożne leksykalne powiązanie wymagania z jawnym elementem planu.", doesNotCount: "Adekwatność planu; powiązanie to kandydat, nie dowód wystarczalności planu.", objectiveEvidence: TEXT_CANDIDATE_PL },
  },
  {
    key: "logic.hypothesis_test_linkage", direction: "higher_is_better", objective: true,
    en: { meaning: "Share of technical hypotheses followed by a discriminating structured check.", question: "Was each technical hypothesis followed by a discriminating structured check?", observationUnit: "one technical hypothesis", direction: HIGHER_EN, counts: "A typed verification episode that can distinguish the hypothesis from alternatives.", doesNotCount: "Chronological proximity or an agent saying it tested something.", objectiveEvidence: TYPED_EVIDENCE_EN },
    pl: { meaning: "Udział hipotez technicznych, po których nastąpiła rozstrzygająca ustrukturyzowana kontrola.", question: "Czy po każdej hipotezie technicznej nastąpiła rozstrzygająca ustrukturyzowana kontrola?", observationUnit: "jedna hipoteza techniczna", direction: HIGHER_PL, counts: "Typowany epizod weryfikacji zdolny odróżnić hipotezę od alternatyw.", doesNotCount: "Bliskość czasowa ani deklaracja agenta, że coś przetestował.", objectiveEvidence: TYPED_EVIDENCE_PL },
  },
  {
    key: "logic.decision_rationale_coverage", direction: "higher_is_better", objective: false,
    en: { meaning: "Share of structured decisions connected to a rationale, alternative, constraint, or evidence.", question: "Were observable decisions connected to a rationale, alternative, constraint, or evidence?", observationUnit: "one structured decision item", direction: HIGHER_EN, counts: "A rationale-bearing structured decision item.", doesNotCount: "Free-text decisions; when the projection exposes no decision items the metric abstains.", objectiveEvidence: "Requires structured decision items from the local projection; without them the metric abstains rather than scoring prose." },
    pl: { meaning: "Udział ustrukturyzowanych decyzji powiązanych z uzasadnieniem, alternatywą, ograniczeniem lub dowodem.", question: "Czy obserwowalne decyzje powiązano z uzasadnieniem, alternatywą, ograniczeniem lub dowodem?", observationUnit: "jeden ustrukturyzowany element decyzji", direction: HIGHER_PL, counts: "Ustrukturyzowany element decyzji niosący uzasadnienie.", doesNotCount: "Decyzje w luźnym tekście; bez elementów decyzji w projekcji metryka wstrzymuje ocenę.", objectiveEvidence: "Wymaga ustrukturyzowanych elementów decyzji z lokalnej projekcji; bez nich metryka wstrzymuje ocenę zamiast punktować prozę." },
  },
  {
    key: "logic.requirement_action_traceability", direction: "higher_is_better", objective: true,
    en: { meaning: "Share of active requirements linked to structured implementation work.", question: "Could every active requirement be linked to structured implementation work?", observationUnit: "one active requirement", direction: HIGHER_EN, counts: "A structured action link (tool, edit, command, or artifact) for the requirement.", doesNotCount: "Generic agent response text reclassified as an action.", objectiveEvidence: TYPED_EVIDENCE_EN },
    pl: { meaning: "Udział aktywnych wymagań powiązanych z ustrukturyzowaną pracą implementacyjną.", question: "Czy każde aktywne wymaganie dało się powiązać z ustrukturyzowaną pracą implementacyjną?", observationUnit: "jedno aktywne wymaganie", direction: HIGHER_PL, counts: "Ustrukturyzowane powiązanie działania (narzędzie, edycja, polecenie lub artefakt) z wymaganiem.", doesNotCount: "Ogólny tekst odpowiedzi agenta przeklasyfikowany na działanie.", objectiveEvidence: TYPED_EVIDENCE_PL },
  },
  {
    key: "logic.open_loop_closure", direction: "higher_is_better", objective: false,
    en: { meaning: "Share of detected questions followed by a related opposite-role response and not reopened.", question: "Were detected questions followed by a related opposite-role response and not reopened?", observationUnit: "one detected question", direction: HIGHER_EN, counts: "A related closing response from the other role that is not reopened later.", doesNotCount: "Answer correctness; a linked response is not proof the answer is right.", objectiveEvidence: TEXT_CANDIDATE_EN },
    pl: { meaning: "Udział wykrytych pytań, po których nastąpiła powiązana odpowiedź drugiej strony bez ponownego otwarcia.", question: "Czy po wykrytych pytaniach nastąpiła powiązana odpowiedź drugiej strony bez ponownego otwarcia?", observationUnit: "jedno wykryte pytanie", direction: HIGHER_PL, counts: "Powiązana zamykająca odpowiedź drugiej roli, nieotwarta ponownie później.", doesNotCount: "Poprawność odpowiedzi; powiązana odpowiedź nie dowodzi, że jest właściwa.", objectiveEvidence: TEXT_CANDIDATE_PL },
  },
  {
    key: "outcome.agent_claim_grounding", direction: "higher_is_better", objective: true,
    en: { meaning: "Share of agent response or summary clauses treated by the shipped compatibility calculator as claim candidates and backed by typed objective evidence.", question: "Which agent response or summary clauses have an authorized objective-evidence link?", observationUnit: "one agent response or summary clause (every such clause is a legacy candidate)", direction: HIGHER_EN, counts: "A candidate clause linked to a typed tool, test, source, or artifact receipt.", doesNotCount: "An assistant statement on its own is never proof of delivery; the shipped compatibility calculator does not detect material claims and conservatively treats every response or summary clause as a candidate.", objectiveEvidence: TYPED_EVIDENCE_EN },
    pl: { meaning: "Udział klauzul odpowiedzi lub podsumowania agenta traktowanych przez dostarczany kalkulator zgodności jako kandydaci deklaracji i popartych typowanym obiektywnym dowodem.", question: "Które klauzule odpowiedzi lub podsumowania agenta mają autoryzowane powiązanie z obiektywnym dowodem?", observationUnit: "jedna klauzula odpowiedzi lub podsumowania agenta (każda jest starszym kandydatem)", direction: HIGHER_PL, counts: "Klauzula kandydata powiązana z typowanym pokwitowaniem narzędzia, testu, źródła lub artefaktu.", doesNotCount: "Sama wypowiedź asystenta nigdy nie dowodzi dostarczenia; dostarczany kalkulator zgodności nie wykrywa istotnych deklaracji i ostrożnie traktuje każdą klauzulę odpowiedzi lub podsumowania jako kandydata.", objectiveEvidence: TYPED_EVIDENCE_PL },
  },
  {
    key: "outcome.verification_strategy_adequacy", direction: "higher_is_better", objective: false,
    en: { meaning: "Share of detected requirements that received a related planned check.", question: "Did each detected requirement receive a related planned check?", observationUnit: "one detected requirement", direction: HIGHER_EN, counts: "A later plan or response with a check cue linked to the requirement.", doesNotCount: "Whether the check ran or passed; this is stated strategy only.", objectiveEvidence: "No execution receipt backs the stated strategy; run and pass evidence belongs to first-pass and verified-coverage metrics." },
    pl: { meaning: "Udział wykrytych wymagań, dla których zaplanowano powiązaną kontrolę.", question: "Czy każde wykryte wymaganie otrzymało powiązaną zaplanowaną kontrolę?", observationUnit: "jedno wykryte wymaganie", direction: HIGHER_PL, counts: "Późniejszy plan lub odpowiedź z sygnałem kontroli powiązanym z wymaganiem.", doesNotCount: "Czy kontrola się wykonała lub przeszła; to tylko deklarowana strategia.", objectiveEvidence: "Deklarowanej strategii nie potwierdza pokwitowanie wykonania; dowody uruchomienia i zaliczenia należą do metryk pierwszego przebiegu i pokrycia zweryfikowanego." },
  },
  {
    key: "outcome.first_pass_verification", direction: "higher_is_better", objective: true,
    en: { meaning: "Whether the first meaningful executable verification episode passed.", question: "Did the first meaningful executable verification episode pass?", observationUnit: "one eligible task with an ordered verification episode", direction: HIGHER_EN, counts: "A first meaningful typed verification episode with a passing outcome.", doesNotCount: "Retries (they cannot improve it) and missing checks (they never become failure).", objectiveEvidence: TYPED_EVIDENCE_EN },
    pl: { meaning: "Czy pierwszy istotny wykonywalny epizod weryfikacji zakończył się powodzeniem.", question: "Czy pierwszy istotny wykonywalny epizod weryfikacji przeszedł?", observationUnit: "jedno kwalifikujące się zadanie z uporządkowanym epizodem weryfikacji", direction: HIGHER_PL, counts: "Pierwszy istotny typowany epizod weryfikacji z wynikiem pozytywnym.", doesNotCount: "Ponowienia (nie poprawiają wyniku) ani brak kontroli (nigdy nie staje się porażką).", objectiveEvidence: TYPED_EVIDENCE_PL },
  },
  {
    key: "outcome.verified_requirement_coverage", direction: "higher_is_better", objective: true,
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

const OBJECTIVE_KEYS = new Set(SEEDS.filter((seed) => seed.objective).map((seed) => seed.key));

export function metricHelpV2IsObjective(metricKey: string): boolean {
  return OBJECTIVE_KEYS.has(metricKey);
}

/** Shipped measurement binding: the versioned coaching definition whose receipts the UI displays. */
export function metricHelpV2Measurement(metricKey: string): MetricHelpMeasurement | null {
  const definition = QUALITY_ANALYSIS_DEFINITIONS.find((candidate) => candidate.key === metricKey);
  if (definition === undefined) return null;
  return {
    definitionVersion: definition.version,
    method: definition.method,
    limitation: definition.limitation,
    objective: OBJECTIVE_KEYS.has(metricKey),
  };
}

export interface ResolvedMetricHelp {
  version: typeof METRIC_HELP_V2_VERSION;
  metricKey: string;
  requestedLocale: MetricHelpLocale;
  locale: MetricHelpLocale;
  fallback: boolean;
  /** Target contract copy. */
  entry: MetricHelpEntry;
  /** Shipped measurement source (English only). */
  measurement: MetricHelpMeasurement | null;
}

/** Resolve help for one metric; unknown or partial locales fall back to English. */
export function metricHelpV2(metricKey: string, locale: MetricHelpLocale = "en"): ResolvedMetricHelp | null {
  const requested = METRIC_HELP_V2[locale] as Readonly<Record<string, MetricHelpEntry>> | undefined;
  const english = METRIC_HELP_V2.en[metricKey];
  if (english === undefined) return null;
  const measurement = metricHelpV2Measurement(metricKey);
  const entry = requested?.[metricKey];
  if (entry === undefined || locale === "en") {
    return { version: METRIC_HELP_V2_VERSION, metricKey, requestedLocale: locale, locale: "en", fallback: locale !== "en", entry: english, measurement };
  }
  return { version: METRIC_HELP_V2_VERSION, metricKey, requestedLocale: locale, locale, fallback: false, entry, measurement };
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
  | "measured";

export interface MetricInspectorInput {
  metricKey: string;
  label: string;
  state: "known" | "unknown" | "not_applicable" | "abstained" | "execution_error" | "pending" | "missing";
  direction: MetricHelpDirection;
  numericValue: number | null;
  numerator: number | null;
  denominator: number | null;
  explanationCode?: string | null;
  /**
   * Factor keys from a loaded PREDICTIVE factor distribution. They are model
   * judgments, never measured evidence, and are only mentioned when an
   * informative experimental estimate is visible.
   */
  experimentalFactorKeys?: readonly string[];
  /** True when an informative experimental estimate is visible for this metric. */
  experimentalVisible?: boolean;
  /** Radar-quality median of a visible estimate (0..1). */
  experimentalMedian?: number | null;
}

export interface MetricInspectorSentences {
  kind: MetricInspectorKind;
  /** What this state or exact value means for the analyzed window. */
  meaning: string;
  /** The safest next action plus how to verify it. */
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
  if (input.state === "pending") return "pending";
  if (input.state !== "known" && input.explanationCode === "episode_horizon_open") return "pending";
  if (input.state === "not_applicable") return "not_applicable";
  if (input.state === "execution_error") return "execution_error";
  if (input.state === "abstained") return "abstained";
  if (input.state === "missing") return input.experimentalVisible ? "experimental" : "missing";
  if (input.state === "unknown") return input.experimentalVisible ? "experimental" : "unknown";
  if (input.numericValue === null) return input.experimentalVisible ? "experimental" : "unknown";
  const radarQuality = input.direction === "lower_is_better" ? 1 - input.numericValue : input.numericValue;
  return radarQuality === 0 ? "zero" : "measured";
}

/**
 * Exactly two deterministic sentences for the selected-metric inspector: what
 * the typed state or exact known value means for the analyzed window, and the safest
 * next action with its verification. No validated quality bands are declared,
 * and predictive factor probabilities are never described as measured.
 */
export function metricInspectorSentences(input: MetricInspectorInput): MetricInspectorSentences {
  const help = metricHelpV2(input.metricKey, "en")?.entry;
  const unit = help?.observationUnit ?? "observation";
  const objective = metricHelpV2IsObjective(input.metricKey) || (input.explanationCode ?? "").includes("objective_");
  const kind = inspectorKind(input);
  const guidance = sessionMetricGuidance(input.metricKey, {
    state: input.state,
    numericValue: input.numericValue,
    direction: input.direction,
    explanationCode: input.explanationCode ?? null,
    factorKeys: [],
    experimentalOnly: kind === "experimental",
  });
  const decision = metricDecisionGuidance(input.metricKey);
  const fraction = input.numerator !== null && input.denominator !== null
    ? `${input.numerator}/${input.denominator} ${unit}`
    : `an unexposed fraction of ${unit}`;
  const factors = input.experimentalVisible ? (input.experimentalFactorKeys ?? []).slice(0, 2).map(readableFactor) : [];
  const experimentalNote = factors.length > 0
    ? ` Separately, the visible experimental estimate's model factor probabilities are lowest for ${factors.join(" and ")} — a model judgment, not measured evidence.`
    : "";
  let meaning: string;
  let action = `${guidance.action.replace(/[.\s]+$/u, "")} — verify: ${lowerFirst(guidance.verification)}`;
  switch (kind) {
    case "pending":
      meaning = `Pending: the newest episode is still open, so ${input.label} cannot be judged yet in the analyzed window; this is open evidence, not a zero and not a measurement.`;
      break;
    case "not_applicable":
      meaning = `Not applicable: no eligible ${unit} was observed in this window, so ${input.label} has nothing to score and no value is implied.`;
      break;
    case "unknown":
      if ((input.explanationCode ?? "").includes("objective_authority") || input.explanationCode === "typed_objective_absent") {
        meaning = `Unknown: the active provider adapter does not expose the authoritative opportunity links and typed receipts ${input.label} requires; prose and model estimates cannot substitute, so this is not a low value.`;
      } else if (input.explanationCode === "opportunity_family_unobservable") {
        meaning = `Unknown: the active provider adapter cannot yet own the typed opportunity family ${input.label} requires; the missing event family is not counted as zero.`;
      } else if (input.explanationCode === "source_reconciliation_incomplete" || input.explanationCode === "semantic_units_unavailable") {
        meaning = `Unknown: semantic-unit reconciliation was not complete for this exact analyzed window, so ${input.label} was withheld instead of scoring a partial source as complete.`;
      } else if (input.explanationCode === "opportunity_set_undetermined") {
        meaning = `Unknown: the task profile did not declare the expected ${unit} set, so ${input.label} has no defensible denominator and was not converted to zero.`;
      } else if (input.explanationCode === "diagnostic_task_not_detected") {
        meaning = `Unknown: this window did not establish that the request was diagnostic, so ${input.label} cannot assume that problem-evidence opportunities applied.`;
      } else {
        meaning = objective
          ? `Unknown: no authoritative typed receipt or link is available for ${input.label} in this sealed receipt; prose is not accepted, so this is missing evidence, not a low value.`
          : `Unknown: this receipt exposes no eligible ${unit} or the event family ${input.label} needs, so no value exists; this is missing evidence, not a low value.`;
      }
      break;
    case "abstained":
      meaning = objective
        ? `Needs evidence: authoritative typed links or receipts are missing for ${input.label}, so the local contract abstained instead of scoring prose.`
        : `Needs evidence: the observed clauses did not support a defensible value for ${input.label}, so the analysis abstained instead of guessing.`;
      break;
    case "execution_error":
      meaning = `Error: the local analysis stage for ${input.label} failed before producing a value; the last valid receipt stands and this is not a low score.`;
      break;
    case "missing":
      meaning = `No record: ${input.label} is not present in this sealed receipt, so nothing was measured or estimated for it.`;
      break;
    case "experimental":
      meaning = `Experimental only: ${input.label} has no measured value in the analyzed window; the visible ${input.experimentalMedian == null ? "estimate" : `${percent(input.experimentalMedian)} radar-quality estimate`} is an uncalibrated model range, not a measurement.${experimentalNote}`;
      break;
    case "zero":
      meaning = input.direction === "lower_is_better"
        ? `Known radar-quality zero: ${fraction} carried the marker (raw ${percent(input.numericValue!)}), so radar quality is 0% and the point sits at the center; a real measured value, not missing data.${experimentalNote}`
        : `Known radar-quality zero: ${fraction} met the versioned local contract for ${input.label}, so the point sits at the radar center; a real measured value, not missing data.${experimentalNote}`;
      break;
    case "measured":
    default: {
      const radarQuality = input.direction === "lower_is_better" ? 1 - input.numericValue! : input.numericValue!;
      meaning = input.direction === "lower_is_better"
        ? `Measured: ${fraction} carried the marker, a raw rate of ${percent(input.numericValue!)} (radar quality ${percent(radarQuality)} because lower is better); this exact versioned candidate value is not a validated quality band.${experimentalNote}`
        : `Measured: ${fraction} met the versioned local contract for ${input.label}, exactly ${percent(radarQuality)}; this versioned candidate value is not a validated quality band or calibrated score.${experimentalNote}`;
      break;
    }
  }
  if (kind === "measured" || kind === "zero") {
    const allMet = input.direction === "lower_is_better"
      ? input.numerator === 0
      : input.numerator !== null && input.numerator === input.denominator;
    action = allMet
      ? `Nothing to change for this window: every observed ${unit} already met the contract, so keep that practice visible — verify: ${lowerFirst(decision.confirmWith)}`
      : `Safest next step: ${lowerFirst(decision.tryNext).replace(/[.\s]+$/u, "")} — verify: ${lowerFirst(decision.confirmWith)}`;
  }
  return { kind, meaning, action, audience: guidance.audience, basis: kind === "measured" || kind === "zero" ? "measured" : guidance.basis };
}
