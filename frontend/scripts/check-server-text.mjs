// Checks the French for server messages (src/lib/serverText.js + src/locales/fr/server.js):
//  1. every user-facing message literal in the backend is translated (fixed text) or matched (pattern);
//  2. English passes every message through unchanged;
//  3. real examples of the variable messages come out in French with their numbers and names kept.
//
//   npm run test:server-text
import { readdirSync, readFileSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createElement } from 'react'
import { renderToString } from 'react-dom/server'
import { createServer } from 'vite'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const backend = join(root, '..', 'backend', 'app')
const vite = await createServer({ root, configFile: false, logLevel: 'error', appType: 'custom', server: { middlewareMode: true, hmr: false } })
let failures = 0
const fail = (msg) => { failures++; console.error(`  FAIL ${msg}`) }

try {
  const i18n = await vite.ssrLoadModule('/src/i18n.jsx')
  const { serverText, PATTERNS } = await vite.ssrLoadModule('/src/lib/serverText.js')
  const setLocale = (loc) => renderToString(createElement(i18n.I18nProvider, { initial: loc })) // sets the module locale

  // 1. Collect message literals from the backend.
  const files = ['routers', 'importers', 'services'].flatMap((d) => readdirSync(join(backend, d)).filter((f) => f.endsWith('.py')).map((f) => join(backend, d, f)))
  files.push(join(backend, 'deps.py'), join(backend, 'main.py'))
  const STR = String.raw`(f?)"((?:[^"\\]|\\.)*)"`
  const SOURCES = [
    new RegExp(String.raw`HTTPException\(\s*\d+,\s*${STR}`, 'g'),
    new RegExp(String.raw`raise [\w.]*Error\(\s*${STR}`, 'g'),
    new RegExp(String.raw`warnings\.append\(\s*${STR}`, 'g'),
    new RegExp(String.raw`JSONResponse\(\{"detail":\s*${STR}`, 'g'),
  ]
  // Not shown in the app: written into the watched folder's "failed" note for the person who dropped the file.
  const NOT_IN_APP = new Set(['No transactions found. ',
    // services/oidc.py: OidcError(code, detail). Only the code reaches the browser, as /login?sso_error=<code>,
    // and pages/Auth.jsx turns it into its own (translated) text; the detail only goes to the server log.
    'bad_nonce', 'invalid_token', 'provider_misconfigured', 'provider_unreachable', 'token_exchange_failed',
    // services/oidc.py: PyJWKClientConnectionError, caught as invalid_token above; logged only.
    "Couldn't fetch the provider's keys: 12",
    // services/backup.py: json.dumps default= hook failing on an unexpected column type, a programming error.
    "can't serialise 12",
  ])
  const sample = (s) => s
    .replace(/\{[^{}]*:\.2f\}/g, '12.00')
    .replace(/\{[^{}]*\}/g, '12')
    .replace(/\\"/g, '"')
  const found = []
  for (const f of files) {
    const src = readFileSync(f, 'utf8')
    for (const re of SOURCES) for (const m of src.matchAll(re)) {
      const text = m[1] ? sample(m[2]) : m[2].replace(/\\"/g, '"')
      if (!NOT_IN_APP.has(text)) found.push({ text, where: relative(join(backend, '..'), f), dynamic: !!m[1] })
    }
  }
  setLocale('fr')
  let fixed = 0; let dynamic = 0
  for (const { text, where, dynamic: dyn } of found) {
    const out = serverText(text)
    if (out === text) fail(`not translated (${where}): ${text}`)
    else if (dyn) dynamic++
    else fixed++
  }
  console.log(`backend messages: ${found.length} found (${new Set(found.map((x) => x.text)).size} distinct), ${fixed} fixed + ${dynamic} with values translated`)

  // 2 + 3. Examples: English unchanged, French as expected.
  const EXAMPLES = [
    ['Row 12: skipped, could not read the date or amount.', 'Ligne 12 : ignorée, date ou montant illisible.'],
    ['Transaction 3: skipped, missing date or amount.', 'Transaction 3 : ignorée, date ou montant manquant.'],
    ['Record 7: skipped, missing date or amount.', 'Enregistrement 7 : ignoré, date ou montant manquant.'],
    ['This file contains amounts in EUR, USD; they will be recorded in the account currency (CAD).', 'Ce fichier contient des montants en EUR, USD; ils seront inscrits dans la devise du compte (CAD).'],
    ['The file says USD but this account is CAD.', 'Le fichier indique USD, mais ce compte est en CAD.'],
    ['The parts add up to 12.00 but the transaction is 15.50.', 'Les parties totalisent 12,00, mais la transaction est de 15,50.'],
    ['You already have a TFSA entry for 2026. Edit that one instead.', 'Vous avez déjà une entrée CÉLI pour 2026. Modifiez plutôt celle-là.'],
    ["That date isn't in 2025. Add it to that year's entry instead.", "Cette date n'est pas en 2025. Ajoutez-la plutôt à l'entrée de cette année-là."],
    ["GoCardless (EU) isn't set up on this server.", "GoCardless (EU) n'est pas configuré sur ce serveur."],
    ['Account not found', 'Compte introuvable'],
    ['SyncConnection not found', 'Connexion bancaire introuvable'],
    ['Entry not found', 'Entrée introuvable'],
    ["Couldn't reach the model: No AI model is set up for your account.", "Impossible de joindre le modèle : Aucun modèle d'IA n'est configuré pour votre compte."],
    ["Couldn't reach OpenAI: [Errno 11001] getaddrinfo failed", 'Impossible de joindre OpenAI : [Errno 11001] getaddrinfo failed'],
    ['OpenAI returned 500: {"error": "boom"}', 'OpenAI a répondu 500 : {"error": "boom"}'],
    ['GoCardless auth failed (401)', "L'authentification GoCardless a échoué (401)."],
    ['SimpleFIN request failed (503)', 'La requête SimpleFIN a échoué (503).'],
    ['No exchange rate for USD→CAD. Amounts in USD are left out of totals until you add one.', "Aucun taux de change pour USD→CAD. Les montants en USD sont exclus des totaux tant que vous n'en ajoutez pas un."],
    ['String should have at least 10 characters', 'Le texte doit contenir au moins 10 caractère(s).'],
    ['Input should be greater than 0', 'La valeur doit être supérieure à 0.'],
    ['Input should be greater than or equal to 0.5', 'La valeur doit être supérieure ou égale à 0,5.'],
    ['Field required', 'Champ obligatoire'],
    ['Nothing to import. The file is empty.', 'Rien à importer. Le fichier est vide.'],
    ['Nothing to import. Row 2: skipped, could not read the date or amount. Row 3: skipped, could not read the date or amount.',
      'Rien à importer. Ligne 2 : ignorée, date ou montant illisible. Ligne 3 : ignorée, date ou montant illisible.'],
    ['String should have at most 120 characters', 'Le texte doit contenir au plus 120 caractère(s).'],
    ['Input should be a valid number, unable to parse string as a number', 'Entrez un nombre valide.'],
    ['Input should be a valid integer, unable to parse string as an integer', 'Entrez un nombre entier.'],
    ['Input should be a valid date or datetime, input is too short', 'Entrez une date valide.'],
    ['Input should be less than or equal to 100', 'La valeur doit être inférieure ou égale à 100.'],
    ['Input should be less than 5', 'La valeur doit être inférieure à 5.'],
    ["String should match pattern '^(checking|savings)$'", "Cette valeur n'est pas acceptée."],
    ['Email or password is incorrect.', 'Le courriel ou le mot de passe est incorrect.'],
    ['Something the server has never said.', 'Something the server has never said.'],
  ]
  for (const [en, fr] of EXAMPLES) {
    const out = serverText(en)
    if (out !== fr) fail(`fr: ${JSON.stringify(en)}\n       got      ${JSON.stringify(out)}\n       expected ${JSON.stringify(fr)}`)
  }
  for (const [re] of PATTERNS) {
    if (!EXAMPLES.some(([en]) => re.test(en)) && !found.some(({ text }) => re.test(text))) console.log(`  note: no example for ${re}`)
  }
  setLocale('en')
  for (const s of [...EXAMPLES.map(([en]) => en), ...found.map((x) => x.text)]) {
    if (serverText(s) !== s) fail(`English changed: ${s}`)
  }
  if (serverText(undefined) !== undefined || serverText(null) !== null) fail('non-strings must pass through')
  console.log(`${Object.keys((await vite.ssrLoadModule('/src/locales/fr/server.js')).default).length} fixed strings in server.js, ${PATTERNS.length} patterns, ${EXAMPLES.length} examples`)
} finally {
  await vite.close()
}
if (failures) { console.error(`${failures} failure(s)`); process.exit(1) }
console.log('server text: all good')
