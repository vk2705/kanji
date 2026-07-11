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
    textHint: "Search by any part of a kanji keyword or alias (e.g. brig → bright)",
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

    studyLanguageLabel: "Study language",
    studyAll: "All",
    studyJapanese: "Japanese (Kanji)",
    studyChineseSimplified: "Chinese (Simplified)",
    studyChineseTraditional: "Chinese (Traditional)",

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

    yourStoryHeading: "Your mnemonic story",
    yourStoryPlaceholder: "Write your own mnemonic for this kanji…",
    otherStoriesHeading: "Other contributors' stories",
    makePublicLabel: "Make public",
    saveBtn: "Save",
    addNamePlaceholder: "Add your name for this part…",
    addBtn: "Add",
    loginHintContribute: "Log in to add your own names and stories.",
  },

  ru: {
    appTitle: "Поиск кандзи RTK",
    appSubtitle: "Ищите кандзи по составляющим их элементам",

    tabParts: "По частям",
    tabText: "По тексту",
    tabChar: "По символу",

    partsHint: "Введите 1–3 названия примитивов RTK (например: sun, mouth, needle)",
    partsPlaceholder: (n) => `Примитив ${n}`,
    textHint: "Поиск по любой части ключевого слова или псевдонима кандзи (например: brig → bright)",
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

    studyLanguageLabel: "Изучаемый язык",
    studyAll: "Все",
    studyJapanese: "Японский (кандзи)",
    studyChineseSimplified: "Китайский (упрощённый)",
    studyChineseTraditional: "Китайский (традиционный)",

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

    yourStoryHeading: "Ваша мнемоническая история",
    yourStoryPlaceholder: "Напишите свою мнемонику для этого кандзи…",
    otherStoriesHeading: "Истории других участников",
    makePublicLabel: "Сделать публичной",
    saveBtn: "Сохранить",
    addNamePlaceholder: "Добавьте своё название для этой части…",
    addBtn: "Добавить",
    loginHintContribute: "Войдите, чтобы добавлять свои названия и истории.",
  },
};

export function t(lang, key, ...args) {
  const entry = translations[lang]?.[key] ?? translations.en[key] ?? key;
  return typeof entry === "function" ? entry(...args) : entry;
}
