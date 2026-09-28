// French for messages the server sends (error details, import warnings, sync and receipt errors).
// The backend speaks English only. Fixed messages are translated through t() with the dictionary in
// locales/fr/server.js; messages with numbers or names inside are matched here, pattern by pattern.
// In English, or when nothing matches, the message is returned exactly as the server sent it.
import { getLocale, t } from '../i18n'

const frNum = (s) => s.replace('.', ',') // 12.00 -> 12,00
// +1,234.56 -> +1 234,56 (the PDF checks send amounts with thousands separators)
const frMoney = (s) => s.replace(/,/g, '\u00a0').replace('.', ',')
const PLAN_KINDS = { TFSA: 'CÉLI', RRSP: 'REER', FHSA: 'CELIAPP' }
// deps.owned() says "<Model> not found" with the SQLAlchemy class name.
const MODELS = {
  Account: 'Compte introuvable', Transaction: 'Transaction introuvable', Category: 'Catégorie introuvable',
  Asset: 'Actif introuvable', Attachment: 'Pièce jointe introuvable', Budget: 'Budget introuvable',
  Goal: 'Objectif introuvable', ImportBatch: 'Importation introuvable', Person: 'Personne introuvable',
  Recurring: 'Opération récurrente introuvable', RegisteredPlan: 'Entrée de régime enregistré introuvable',
  Rule: 'Règle introuvable', Settlement: 'Remboursement introuvable', SyncConnection: 'Connexion bancaire introuvable',
  User: 'Utilisateur introuvable', Security: 'Titre introuvable', Holding: 'Position introuvable',
  InvestmentActivity: 'Opération introuvable', InvestImport: 'Importation introuvable', ChargeAlert: 'Alerte introuvable',
}
// Investment activity kinds in "a <kind> needs a quantity…" (importers/holdings.py)
const TRADE_KINDS = { buy: 'un achat', sell: 'une vente' }
// net.validate_outbound_url(label=…): the label starts the sentence.
const URL_LABELS = {
  URL: "L'adresse", 'The ntfy address': "L'adresse ntfy",
  'SimpleFIN setup token': 'Le jeton de configuration SimpleFIN', 'SimpleFIN access URL': "L'adresse d'accès SimpleFIN",
}
const urlLabel = (s) => URL_LABELS[s] ?? s
// PDF statement checks (importers/pdf.py): what the statement lists, and the advice that ends each warning.
const PDF_TOTALS = {
  'total deposits': 'un total des dépôts', 'total withdrawals': 'un total des retraits',
  'purchases & debits': 'des achats et débits', 'payments & credits': 'des paiements et crédits',
}
const PDF_ADVICE = {
  'Some rows may be missing or extra; check the preview.': "Des lignes sont peut-être manquantes ou en trop; vérifiez l'aperçu.",
  'Some rows may be missing, extra or have the wrong sign; check the preview.': "Des lignes sont peut-être manquantes, en trop ou de signe inversé; vérifiez l'aperçu.",
}
const pdfAdvice = (s) => (s ? ` ${PDF_ADVICE[s] ?? s}` : '')

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
  // "Nothing to import. " followed by up to three of the warnings above (some warnings are two sentences)
  [/^Nothing to import\. ?([\s\S]*)$/, (m) => ['Rien à importer.', ...sentences(m[1])].join(' ')],
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
  // Investments (importers/holdings.py, routers/investments.py)
  [/^Row (\d+): split without a ratio was skipped\. Add it by hand\.$/, 'Ligne {1} : fractionnement sans ratio ignoré. Ajoutez-le à la main.'],
  [/^Row (\d+): skipped, an? (\S+) needs a quantity and a price or amount\.$/,
    (m) => `Ligne ${m[1]} : ignorée, ${TRADE_KINDS[m[2]] ?? `une opération « ${m[2]} »`} exige une quantité et un prix ou un montant.`],
  [/^Row (\d+): skipped, no amount\.$/, 'Ligne {1} : ignorée, aucun montant.'],
  [/^Row (\d+): skipped, no symbol\.$/, 'Ligne {1} : ignorée, aucun symbole.'],
  [/^(.+): book cost missing or in another currency without a rate; set to 0\.$/,
    '{1} : coût comptable manquant ou dans une autre devise sans taux de change; mis à 0.'],
  // PDF statement checks (importers/pdf.py). Amounts come as +1,234.56. The backend builds these from two string
  // pieces, so the second piece is optional here (the checker only sees the first); each pattern still ends at the
  // message's own last word, so warnings joined after "Nothing to import." stay separate.
  [/^Running balance check failed near ([^"]+?) "(.{0,40})": the balance moved by (\S+) ?(?:but the rows read add up to (\S+)\. Rows may be missing, misread or have the wrong sign; check them\.)?$/,
    (m) => `La vérification du solde courant a échoué près ${m[1] === '?' ? 'de' : `du ${m[1]},`} « ${m[2]} » : le solde a varié de ${frMoney(m[3])}, `
      + `mais les lignes lues totalisent ${frMoney(m[4] ?? '?')}. Des lignes sont peut-être manquantes, mal lues ou de signe inversé; vérifiez-les.`],
  [/^The running balance did not reconcile in (\d+) more places\.$/, 'Le solde courant ne concorde pas à {1} autre(s) endroit(s).'],
  [/^(\d+) of (\d+) rows could not be checked against the running balance, so their ?(?:sign \(money in or out\) was taken from the column or the wording\. Check them in the preview\.)?$/,
    "{1} ligne(s) sur {2} n'ont pas pu être vérifiées d'après le solde courant; leur signe (entrée ou sortie d'argent) a donc été "
      + "déduit de la colonne ou du libellé. Vérifiez-les dans l'aperçu."],
  [/^This PDF shows no running balance, so each row's sign \(money in or out\) was taken from the column ?(?:or the wording and could not be verified\. Check the preview\.)?$/,
    "Ce PDF n'affiche aucun solde courant; le signe de chaque ligne (entrée ou sortie d'argent) a donc été déduit de la colonne "
      + "ou du libellé et n'a pas pu être vérifié. Vérifiez l'aperçu."],
  [/^The statement's opening balance \(([^)]*)\) and closing balance ?(?:\(([^)]*)\) differ by (\S+), but the rows found add up to (\S+)\.)? ?(Some rows may be missing[^;]*; check the preview\.)?$/,
    (m) => `Le solde d'ouverture (${frMoney(m[1])}) et le solde de clôture (${frMoney(m[2] ?? '?')}) du relevé diffèrent de `
      + `${frMoney(m[3] ?? '?')}, mais les lignes trouvées totalisent ${frMoney(m[4] ?? '?')}.${pdfAdvice(m[5])}`],
  [/^The statement lists ([^.]+?) of (\S+), but the rows found ?(?:add up ?(?:to (\S+)\.)?)? ?(Some rows may be missing[^;]*; check the preview\.)?$/,
    (m) => `Le relevé indique ${PDF_TOTALS[m[1]] ?? m[1]} de ${frMoney(m[2])}, mais les lignes trouvées totalisent `
      + `${frMoney(m[3] ?? '?')}.${pdfAdvice(m[4])}`],
  [/^The statement goes from a previous balance of (\S+) to a new balance of ?(?:(\S+) \((\S+)\), but the rows found change it by (\S+)\.)? ?(Some rows may be missing[^;]*; check the preview\.)?$/,
    (m) => `Le relevé passe d'un solde précédent de ${frMoney(m[1])} à un nouveau solde de ${frMoney(m[2] ?? '?')} `
      + `(${frMoney(m[3] ?? '?')}), mais les lignes trouvées le font varier de ${frMoney(m[4] ?? '?')}.${pdfAdvice(m[5])}`],
  [/^The statement's own summary figures \(previous balance, payments, purchases, ?(?:interest, fees, new balance\) don't add up as read, so the PDF text may have been misread\. Check the preview\.)?$/,
    "Les chiffres du sommaire du relevé (solde précédent, paiements, achats, intérêts, frais, nouveau solde) ne concordent pas "
      + "tels qu'ils ont été lus; le texte du PDF a peut-être été mal lu. Vérifiez l'aperçu."],
  [/^Skipped (\d+) PDF rows that did not have a readable date or amount\.$/, '{1} ligne(s) du PDF ignorée(s) : date ou montant illisible.'],
  [/^PDF import is best-effort, but every row's sign was confirmed by the running balance ?(?:and the rows match the statement's balances\.)?$/,
    "L'importation PDF est approximative, mais le signe de chaque ligne a été confirmé par le solde courant et les lignes "
      + 'concordent avec les soldes du relevé.'],
  [/^PDF import is best-effort, but these rows match the statement's own totals\.$/,
    "L'importation PDF est approximative, mais ces lignes concordent avec les totaux du relevé."],
  [/^PDF import is best-effort\. Check the preview carefully; ?(?:QFX\/OFX or CSV exports from your bank are safer when they are available\.)?$/,
    "L'importation PDF est approximative. Vérifiez attentivement l'aperçu; les exportations QFX/OFX ou CSV de votre banque "
      + "sont plus sûres lorsqu'elles sont offertes."],
  // AI search (routers/ai_tools.py): the model's error comes first.
  [/^([\s\S]*?) ?Try rephrasing, or use the filters\.$/, (m) => `${m[1] ? `${serverText(m[1])} ` : ''}Reformulez ou utilisez les filtres.`],
  // Backups (routers/backups.py, services/backup.py)
  [/^Use at least (\d+) characters for the backup passphrase\.$/, 'Utilisez au moins {1} caractères pour la phrase de passe de sauvegarde.'],
  [/^Saved locally, but the S3 copy failed: ([\s\S]*)$/, (m) => `Sauvegarde enregistrée localement, mais la copie S3 a échoué : ${serverText(m[1])}`],
  [/^S3 (\S+) failed: HTTP (\d+)((?: \([^)]*\))?)$/, 'La requête S3 {1} a échoué : HTTP {2}{3}'],
  // Safe outbound addresses (services/net.py, services/sync.py)
  [/^SimpleFIN returned an unsafe access URL: ([\s\S]*)$/, (m) => `SimpleFIN a renvoyé une adresse d'accès non sécuritaire : ${serverText(m[1])}`],  // before the "<label> …" patterns below
  [/^(.+) must start with http:\/\/ or https:\/\/\.$/, (m) => `${urlLabel(m[1])} doit commencer par http:// ou https://.`],
  [/^(.+) must be a public internet address, not a local network host\.$/,
    (m) => `${urlLabel(m[1])} doit être une adresse Internet publique, et non un hôte du réseau local.`],
  [/^(.+) resolves to a private network address\.$/, (m) => `${urlLabel(m[1])} correspond à une adresse de réseau privé.`],
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

// Translates warnings joined with spaces: at each point, the longest run of sentences that is a known message.
function sentences(text) {
  const parts = text.split(/(?<=\.) (?=\S)/).filter(Boolean)
  const out = []
  for (let i = 0; i < parts.length;) {
    let j = parts.length
    for (; j > i + 1; j--) {
      const run = parts.slice(i, j).join(' ')
      if (serverText(run) !== run) break
    }
    out.push(serverText(parts.slice(i, j).join(' ')))
    i = j
  }
  return out
}

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
