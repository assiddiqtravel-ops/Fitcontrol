import React, { useMemo, useState } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { I18nContext, Lang, translate } from "./i18n";
import { AppProvider } from "./state";
import { detectLanguage, initTelegram } from "./telegram";
import "./styles.css";

initTelegram();

function Root() {
  const [lang, setLangState] = useState<Lang>(detectLanguage());
  const value = useMemo(
    () => ({
      lang,
      setLang: (l: Lang) => {
        setLangState(l);
        localStorage.setItem("fc_lang", l);
        document.documentElement.lang = l;
      },
      t: (key: string) => translate(lang, key),
    }),
    [lang]
  );
  return (
    <I18nContext.Provider value={value}>
      <AppProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </AppProvider>
    </I18nContext.Provider>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>
);
