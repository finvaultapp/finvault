// French for messages the server sends (error details, import warnings, sync and receipt errors).
// The backend speaks English only. Fixed messages are translated through t() with the dictionary in
// locales/fr/server.js; messages with numbers or names inside are matched here, pattern by pattern.
// In English, or when nothing matches, the message is returned exactly as the server sent it.
import { getLocale, t } from '../i18n'

const frNum = (s) => s.replace('.', ',') // 12.00 -> 12,00
const PLAN_KINDS = { TFSA: 'CÉLI', RRSP: 'REER', FHSA: 'CELIAPP' }
// deps.owned() says "<Model> not found" with the SQLAlchemy class name.
const MODELS = {
  Account: 'Compte introuvable', Transaction: 'Transaction introuvable', Category: 'Catégorie introuvable',
  Asset: 'Actif introuvable', Attachment: 'Pièce jointe introuvable', Budget: 'Budget introuvable',
  Goal: 'Objectif introuvable', ImportBatch: 'Importation introuvable', Person: 'Personne introuvable',
  Recurring: 'Opération récurrente introuvable', RegisteredPlan: 'Entrée de régime enregistré introuvable',
  Rule: 'Règle introuvable', Settlement: 'Remboursement introuvable', SyncConnection: 'Connexion bancaire introuvable',
  User: 'Utilisateur introuvable',
}

// [pattern, French]. In the French, {1}, {2}… are the captured groups as sent; a function gets the match.
// Groups that carry another server message (the reason after "Couldn't reach …:") are translated too.
export const PATTERNS = [
  // Import warnings (importers/*.py, routers/imports.py)
  [/^Row (\d+): skipped, could not read the date or amount\.$/, 'Ligne {1} : ignorée, date ou montant illisible.'],
  [/^Transaction (\d+): skipped, missing date or amount\.$/, 'Transaction {1} : ignorée, date ou montant manquant.'],
  [/^Record (\d+): skipped, missing date or amount\.$/, 'Enregistrement {1} : ignoré, date ou montant manquant.'],
  [/^This file contains amounts in (.+); they will be recorded in the account currency \(([^)]+)\)\.$/,
    'Ce fichier contient des montants en {1}; ils seront inscrits dans la devise du compte ({2}).'],
  [/^The file says (\S+) but this account is (\S+)\.$/, 'Le fichier indique {1}, mais ce compte est en {2}.'],
  // "Nothing to import. " followed by up to three of the warnings above
  [/^Nothing to import\. ?([\s\S]*)$/, (m) => ['Rien à importer.', ...m[1].split(/(?<=\.) (?=\S)/).filter(Boolean).map(serverText)].join(' ')],
  // Splits, registered plans, sync (routers/*.py)
  [/^The parts add up to (-?\d+\.\d+) but the transaction is (-?\d+\.\d+)\.$/,
    (m) => `Les parties totalisent ${frNum(m[1])}, mais la transaction est de ${frNum(m[2])}.`],
  [/^You already have a (\w+) entry for (\d+)\. Edit that one instead\.$/,
    (m) => `Vous avez déjà une entrée ${PLAN_KINDS[m[1]] ?? m[1]} pour ${m[2]}. Modifiez plutôt celle-là.`],
  [/^That date isn't in (\d+)\. Add it to that year's entry instead\.$/,
    "Cette date n'est pas en {1}. Ajoutez-la plutôt à l'entrée de cette année-là."],
  [/^(.+) isn't set up on this server\.$/, "{1} n'est pas configuré sur ce serveur."],
  [/^(\w+) not found$/, (m) => MODELS[m[1]] ?? `${m[1]} introuvable`],
  // Remote services; the part after the colon comes from elsewhere and is translated when we know it.
  [/^Couldn't reach OpenAI: ([\s\S]*)$/, (m) => `Impossible de joindre OpenAI : ${serverText(m[1])}`],
  [/^Couldn't reach the model: ([\s\S]*)$/, (m) => `Impossible de joindre le modèle : ${serverText(m[1])}`],
  [/^Couldn't reach the rate service: ([\s\S]*)$/, (m) => `Impossible de joindre le service des taux : ${serverText(m[1])}`],
  [/^Invalid pattern: ([\s\S]*)$/, 'Motif invalide : {1}'],
  [/^OpenAI returned (\d+): ([\s\S]*)$/, 'OpenAI a répondu {1} : {2}'],
  [/^The model server returned (\d+): ([\s\S]*)$/, 'Le serveur du modèle a répondu {1} : {2}'],
  [/^GoCardless auth failed \((\d+)\)$/, "L'authentification GoCardless a échoué ({1})."],
  [/^GoCardless could not start the connection: ([\s\S]*)$/, "GoCardless n'a pas pu établir la connexion : {1}"],
  [/^GoCardless transactions failed \((\d+)\)$/, 'La récupération des transactions GoCardless a échoué ({1}).'],
  [/^Pluggy auth failed \((\d+)\)$/, "L'authentification Pluggy a échoué ({1})."],
  [/^SimpleFIN request failed \((\d+)\)$/, 'La requête SimpleFIN a échoué ({1}).'],
  [/^No exchange rate for (.+)\. Amounts in (.+) are left out of totals until you add one\.$/,
    "Aucun taux de change pour {1}. Les montants en {2} sont exclus des totaux tant que vous n'en ajoutez pas un."],
  // Generic form validation from the server (pydantic)
  [/^String should have at least (\d+) characters?$/, 'Le texte doit contenir au moins {1} caractère(s).'],
  [/^String should have at most (\d+) characters?$/, 'Le texte doit contenir au plus {1} caractère(s).'],
  [/^String should match pattern '.*'$/, "Cette valeur n'est pas acceptée."],
  [/^Input should be greater than or equal to (-?[\d.]+)$/, (m) => `La valeur doit être supérieure ou égale à ${frNum(m[1])}.`],
  [/^Input should be greater than (-?[\d.]+)$/, (m) => `La valeur doit être supérieure à ${frNum(m[1])}.`],
  [/^Input should be less than or equal to (-?[\d.]+)$/, (m) => `La valeur doit être inférieure ou égale à ${frNum(m[1])}.`],
  [/^Input should be less than (-?[\d.]+)$/, (m) => `La valeur doit être inférieure à ${frNum(m[1])}.`],
  [/^Input should be a valid (?:number|decimal)\b[\s\S]*$/, 'Entrez un nombre valide.'],
  [/^Input should be a valid integer\b[\s\S]*$/, 'Entrez un nombre entier.'],
  [/^Input should be a valid date\b[\s\S]*$/, 'Entrez une date valide.'],
]

export function serverText(msg) {
  if (typeof msg !== 'string' || getLocale() !== 'fr') return msg
  const direct = t(msg)
  if (direct !== msg) return direct
  for (const [re, fr] of PATTERNS) {
    const m = re.exec(msg)
    if (m) return typeof fr === 'function' ? fr(m) : fr.replace(/\{(\d)\}/g, (_, i) => m[i] ?? '')
  }
  return msg
}
