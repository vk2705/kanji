function ruPlural(n, one, few, many) {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if ([2, 3, 4].includes(mod10) && ![12, 13, 14].includes(mod100)) return few;
  return many;
}

export const translations = {
  en: {
    appTitle: "RTK Kanji Search",
    appSubtitle: "Search kanji by their primitive elements",

    tabParts: "By Parts",
    tabText: "By Text",
    tabChar: "By Character",

    partsHint: "Enter 1–3 RTK primitive names (e.g. sun, mouth, needle)",
    partsPlaceholder: (n) => `Primitive ${n}`,
    textHint: "Search by a whole word in a kanji keyword or alias (e.g. hat, bright)",
    textPlaceholder: "Type to search…",
    charHint: "Paste a kanji character to look it up (e.g. 明)",
    charPlaceholder: "paste kanji here…",
    searchBtn: "Search",
    fallbackMsg: (term) => `No kanji use "${term}" as a primitive. Showing keyword matches instead:`,

    searching: "Searching…",
    noResults: "No results found.",
    resultCount: (n) => `${n} result${n !== 1 ? "s" : ""}`,

    loading: "Loading…",
    errorPrefix: (msg) => `Error: ${msg}`,
    backBtn: "← Back",
    rtkFrame: (n) => `RTK #${n}`,
    strokesLabel: (n) => `${n} strokes`,
    aliasesHeading: "Aliases / names",
    madeFromHeading: "Made from",
    expandPart: "Show this part's own breakdown",
    collapsePart: "Hide this part's own breakdown",

    studyLanguageLabel: "Study language",
    studyAll: "All",
    studyJapanese: "Japanese (Kanji)",
    studyChineseSimplified: "Chinese (Simplified)",
    studyChineseTraditional: "Chinese (Traditional)",

    sourcesLabel: "Sources",
    sourceSystem: "Official (Heisig / system)",
    sourceCommunity: "Community contributions",
    sourceMine: "My own",

    loginRegisterBtn: "Log in / Register",
    loginTab: "Log in",
    registerTab: "Register",
    usernamePlaceholder: "Username",
    passwordPlaceholder: "Password",
    passwordPlaceholderRegister: "Password (min 8 chars)",
    loginSubmit: "Log in",
    registerSubmit: "Create account",
    cancelBtn: "Cancel",
    logoutBtn: "Log out",
    authDividerOr: "or",

    yourStoryHeading: "Your mnemonic story",
    yourStoryPlaceholder: "Write your own mnemonic for this kanji…",
    otherStoriesHeading: "Other contributors' stories",
    makePublicLabel: "Make public",
    saveBtn: "Save",
    addNamePlaceholder: "Add your name for this part…",
    addKanjiNamePlaceholder: "Add your own name for this kanji…",
    addBtn: "Add",
    loginHintContribute: "Log in to add your own names and stories.",

    newKanjiBtn: "+ New kanji",
    myContributionsBtn: "My contributions",

    createKanjiHeading: "Create a new kanji / hanzi",
    keywordPlaceholder: "Keyword (e.g. bright)",
    characterPlaceholder: "Character (leave blank if none)",
    scriptLabel: "Script",
    makePrivateCheckbox: "Keep private",
    createSubmit: "Create",
    createdKanjiNote: "Created. Add a picture and/or a decomposition below, or you're done.",
    doneBtn: "Done",

    uploadImageHeading: "Picture (for primitives with no real character)",
    uploadImageHint: "GIF, PNG, JPEG, or WebP, up to 2MB.",
    uploadBtn: "Upload",

    addDecompositionHeading: "Add alternate decomposition",
    decompositionPartsPlaceholder: "Parts, comma-separated (e.g. sun, moon)",
    decompositionLabelPlaceholder: "Label (optional)",
    addDecompositionSubmit: "Add decomposition",

    myContributionsHeading: "My contributions",
    contribKanjiHeading: "Kanji you created",
    contribDecompositionsHeading: "Decompositions you added",
    contribAliasesHeading: "Names you added",
    contribStoriesHeading: "Stories you wrote",
    noContributions: "You haven't contributed anything yet.",
    visibilityPublicLabel: "Public",
    visibilityPrivateLabel: "Private",
  },

  ru: {
    appTitle: "Поиск кандзи RTK",
    appSubtitle: "Ищите кандзи по составляющим их элементам",

    tabParts: "По частям",
    tabText: "По тексту",
    tabChar: "По символу",

    partsHint: "Введите 1–3 названия примитивов RTK (например: sun, mouth, needle)",
    partsPlaceholder: (n) => `Примитив ${n}`,
    textHint: "Поиск по целому слову в ключевом слове или псевдониме кандзи (например: hat, bright)",
    textPlaceholder: "Введите текст для поиска…",
    charHint: "Вставьте символ кандзи, чтобы найти его (например: 明)",
    charPlaceholder: "вставьте кандзи сюда…",
    searchBtn: "Найти",
    fallbackMsg: (term) => `Ни один кандзи не использует «${term}» как примитив. Показаны совпадения по ключевым словам:`,

    searching: "Поиск…",
    noResults: "Ничего не найдено.",
    resultCount: (n) => `${n} ${ruPlural(n, "результат", "результата", "результатов")}`,

    loading: "Загрузка…",
    errorPrefix: (msg) => `Ошибка: ${msg}`,
    backBtn: "← Назад",
    rtkFrame: (n) => `RTK №${n}`,
    strokesLabel: (n) => `${ruPlural(n, "черта", "черты", "черт")}: ${n}`,
    aliasesHeading: "Псевдонимы / названия",
    madeFromHeading: "Состоит из",
    expandPart: "Показать разбор этой части",
    collapsePart: "Скрыть разбор этой части",

    studyLanguageLabel: "Изучаемый язык",
    studyAll: "Все",
    studyJapanese: "Японский (кандзи)",
    studyChineseSimplified: "Китайский (упрощённый)",
    studyChineseTraditional: "Китайский (традиционный)",

    sourcesLabel: "Источники",
    sourceSystem: "Официальные (Хайсиг / система)",
    sourceCommunity: "Вклад сообщества",
    sourceMine: "Мои собственные",

    loginRegisterBtn: "Войти / Зарегистрироваться",
    loginTab: "Вход",
    registerTab: "Регистрация",
    usernamePlaceholder: "Имя пользователя",
    passwordPlaceholder: "Пароль",
    passwordPlaceholderRegister: "Пароль (мин. 8 символов)",
    loginSubmit: "Войти",
    registerSubmit: "Создать аккаунт",
    cancelBtn: "Отмена",
    logoutBtn: "Выйти",
    authDividerOr: "или",

    yourStoryHeading: "Ваша мнемоническая история",
    yourStoryPlaceholder: "Напишите свою мнемонику для этого кандзи…",
    otherStoriesHeading: "Истории других участников",
    makePublicLabel: "Сделать публичной",
    saveBtn: "Сохранить",
    addNamePlaceholder: "Добавьте своё название для этой части…",
    addKanjiNamePlaceholder: "Добавьте своё название для этого кандзи…",
    addBtn: "Добавить",
    loginHintContribute: "Войдите, чтобы добавлять свои названия и истории.",

    newKanjiBtn: "+ Новый кандзи",
    myContributionsBtn: "Мой вклад",

    createKanjiHeading: "Создать новый кандзи / ханьцзы",
    keywordPlaceholder: "Ключевое слово (например: bright)",
    characterPlaceholder: "Символ (оставьте пустым, если его нет)",
    scriptLabel: "Письменность",
    makePrivateCheckbox: "Оставить приватным",
    createSubmit: "Создать",
    createdKanjiNote: "Создано. Добавьте картинку и/или разбор ниже, либо завершите.",
    doneBtn: "Готово",

    uploadImageHeading: "Картинка (для примитивов без настоящего символа)",
    uploadImageHint: "GIF, PNG, JPEG или WebP, до 2 МБ.",
    uploadBtn: "Загрузить",

    addDecompositionHeading: "Добавить альтернативный разбор",
    decompositionPartsPlaceholder: "Части через запятую (например: sun, moon)",
    decompositionLabelPlaceholder: "Метка (необязательно)",
    addDecompositionSubmit: "Добавить разбор",

    myContributionsHeading: "Мой вклад",
    contribKanjiHeading: "Созданные вами кандзи",
    contribDecompositionsHeading: "Добавленные вами разборы",
    contribAliasesHeading: "Добавленные вами названия",
    contribStoriesHeading: "Написанные вами истории",
    noContributions: "Вы пока ничего не добавили.",
    visibilityPublicLabel: "Публично",
    visibilityPrivateLabel: "Приватно",
  },
};

export function t(lang, key, ...args) {
  const entry = translations[lang]?.[key] ?? translations.en[key] ?? key;
  return typeof entry === "function" ? entry(...args) : entry;
}
