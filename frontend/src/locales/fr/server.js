// Canadian French for fixed messages the server sends: error details (routers/*.py, deps.py, main.py),
// errors raised in services and importers that reach the user, and import warnings.
// Keys are the exact English strings from the backend. Messages with numbers or names inside are in
// lib/serverText.js. The Canadian bank-sync block message lives in setup.js.
export default {
  // deps.py and main.py
  "Not signed in": "Vous n'êtes pas connecté.",
  "Session expired": "Votre session a expiré. Connectez-vous de nouveau.",
  "Admins only": "Réservé aux administrateurs.",
  "Missing X-FinVault header": "En-tête X-FinVault manquant.",
  "Not found": "Introuvable",

  // Sign-in and account (routers/auth.py, routers/admin.py)
  "Use at least 10 characters for your password.": "Utilisez au moins 10 caractères pour votre mot de passe.",
  "Enter a valid email address.": "Entrez une adresse courriel valide.",
  "Registration is closed. Ask your admin to create an account for you.": "Les inscriptions sont fermées. Demandez à votre administrateur de vous créer un compte.",
  "A valid invite code is required to register.": "Un code d'invitation valide est requis pour s'inscrire.",
  "An account with this email already exists.": "Un compte existe déjà avec cette adresse courriel.",
  "Too many attempts. Wait 15 minutes and try again.": "Trop de tentatives. Attendez 15 minutes et réessayez.",
  "Email or password is incorrect.": "Le courriel ou le mot de passe est incorrect.",
  "Sign-in expired. Enter your password again.": "La connexion a expiré. Entrez de nouveau votre mot de passe.",
  "That code didn't work. Check your authenticator app's time is correct.": "Ce code n'a pas fonctionné. Vérifiez que l'heure de votre application d'authentification est exacte.",
  "Current password is incorrect.": "Le mot de passe actuel est incorrect.",
  "Two-factor login is already on.": "La connexion à deux facteurs est déjà activée.",
  "That code didn't match. Try the next one your app shows.": "Ce code ne correspond pas. Essayez le prochain code affiché par votre application.",
  "Password is incorrect.": "Le mot de passe est incorrect.",
  "That code didn't match.": "Ce code ne correspond pas.",
  "User not found": "Utilisateur introuvable",
  "There must be at least one active admin.": "Il doit rester au moins un administrateur actif.",
  "You can't delete your own account here.": "Vous ne pouvez pas supprimer votre propre compte ici.",
  "The AI endpoint must start with http:// or https://": "L'adresse du service d'IA doit commencer par http:// ou https://",

  // AI chat (routers/ai.py, services/ai.py)
  "Your admin hasn't allowed personal OpenAI keys on this server.": "Votre administrateur n'a pas autorisé les clés OpenAI personnelles sur ce serveur.",
  "Add your OpenAI API key first.": "Ajoutez d'abord votre clé d'API OpenAI.",
  "AI chat isn't set up for your account. Choose a model in Settings.": "Le clavardage IA n'est pas configuré pour votre compte. Choisissez un modèle dans les paramètres.",
  "Turn on AI chat in Settings first. It's off until you choose to share your data with the model.": "Activez d'abord le clavardage IA dans les paramètres. Il reste désactivé tant que vous n'acceptez pas de partager vos données avec le modèle.",
  "OpenAI didn't accept that key. Copy it again from platform.openai.com/api-keys.": "OpenAI n'a pas accepté cette clé. Copiez-la de nouveau depuis platform.openai.com/api-keys.",
  "No AI model is set up for your account.": "Aucun modèle d'IA n'est configuré pour votre compte.",

  // Accounts, categories, budgets, goals, plans
  "The statement date is before the account's opening date.": "La date du relevé est antérieure à la date d'ouverture du compte.",
  "Value not found": "Valeur introuvable",
  "A category can't be its own parent.": "Une catégorie ne peut pas être sa propre catégorie parente.",
  "A rule needs to set a category or a payee.": "Une règle doit définir une catégorie ou un bénéficiaire.",
  "Budgets can only be set on expense categories.": "Les budgets ne s'appliquent qu'aux catégories de dépenses.",
  "This goal tracks a linked account's balance; move money into that account instead.": "Cet objectif suit le solde d'un compte lié; transférez plutôt de l'argent dans ce compte.",
  "Entry not found": "Entrée introuvable",

  // Currency (routers/currency.py)
  "Pick two different currencies.": "Choisissez deux devises différentes.",
  "Fetching rates is turned off. An admin can enable it in Admin → Settings.": "La récupération des taux est désactivée. Un administrateur peut l'activer dans Administration → Paramètres.",

  // Receipts and reminders (routers/extras.py, services/receipts.py)
  "The file is missing from the server's data folder.": "Le fichier est introuvable dans le dossier de données du serveur.",
  "Receipt text reading is turned off. An admin can enable it.": "La lecture du texte des reçus est désactivée. Un administrateur peut l'activer.",
  "Receipts can be up to 10 MB.": "Les reçus peuvent faire jusqu'à 10 Mo.",
  "Use a JPG, PNG, WebP, HEIC photo or a PDF.": "Utilisez une photo JPG, PNG, WebP ou HEIC, ou un PDF.",
  "This PDF is a scan without text; attach it as a photo to read it.": "Ce PDF est une numérisation sans texte; joignez-le comme photo pour le lire.",
  "Tesseract isn't installed on this server.": "Tesseract n'est pas installé sur ce serveur.",
  "The ntfy address should look like https://ntfy.sh/your-private-topic.": "L'adresse ntfy devrait ressembler à https://ntfy.sh/votre-sujet-prive.",
  "Nothing was sent. Check the ntfy address, or ask your admin to set up email.": "Rien n'a été envoyé. Vérifiez l'adresse ntfy ou demandez à votre administrateur de configurer le courriel.",

  // Shared costs and transfers (routers/sharing.py, services/transfers.py)
  "A split needs at least two parts. To change the category, just pick one.": "Une répartition doit avoir au moins deux parties. Pour changer la catégorie, choisissez-en simplement une.",
  "You can only share a payment you made (money out).": "Vous ne pouvez partager qu'un paiement que vous avez fait (sortie d'argent).",
  "Shares can't add up to more than the payment.": "Les parts ne peuvent pas dépasser le montant du paiement.",
  "Pick the money-out line first and the money-in line second.": "Choisissez d'abord la ligne de sortie d'argent, puis la ligne d'entrée.",
  "Those two transactions can't be a transfer between your own accounts.": "Ces deux transactions ne peuvent pas être un virement entre vos propres comptes.",

  // Bank sync (services/sync.py, routers/sync.py)
  "Pluggy item not found. Copy the item ID from your Pluggy/MeuPluggy dashboard.": "Élément Pluggy introuvable. Copiez l'identifiant de l'élément depuis votre tableau de bord Pluggy/MeuPluggy.",
  "That doesn't look like a SimpleFIN setup token.": "Cela ne ressemble pas à un jeton de configuration SimpleFIN.",
  "SimpleFIN setup token must point to an https URL.": "Le jeton de configuration SimpleFIN doit pointer vers une adresse https.",
  "SimpleFIN rejected the token. Setup tokens can only be claimed once; create a new one.": "SimpleFIN a refusé le jeton. Un jeton de configuration ne peut être utilisé qu'une fois; créez-en un nouveau.",
  "Bank sync is turned off by the admin.": "La synchro bancaire a été désactivée par l'administrateur.",
  "That account wasn't found at the provider.": "Ce compte est introuvable chez le fournisseur.",

  // Importing files (importers/*.py)
  "File is larger than 15 MB.": "Le fichier dépasse 15 Mo.",
  "Unsupported file. Use OFX, QFX, QBO, QIF or CSV. PDF statements can't be imported.": "Fichier non pris en charge. Utilisez OFX, QFX, QBO, QIF ou CSV. Les relevés PDF ne peuvent pas être importés.",
  "The file is empty.": "Le fichier est vide.",
  "Could not find the date and amount columns. Pick them in the column mapping.": "Impossible de trouver les colonnes de date et de montant. Choisissez-les dans l'association des colonnes.",
  "Could not recognise the date format. Choose one in the preview.": "Format de date non reconnu. Choisissez-en un dans l'aperçu.",
  "Amounts were all positive, so the transaction type column was used to set the sign.": "Tous les montants étaient positifs; la colonne du type de transaction a donc servi à déterminer le signe.",
  "Most amounts are positive on a credit card, so purchases were treated as spending (amounts flipped). Turn off \"Flip signs\" if that is wrong.": "La plupart des montants sont positifs sur une carte de crédit; les achats ont donc été traités comme des dépenses (signes inversés). Désactivez « Inverser les signes » si c'est une erreur.",
  "Dates could be month-first or day-first. Assumed month/day/year; change it if that is wrong.": "Les dates pourraient commencer par le mois ou par le jour. Le format mois/jour/année a été retenu; changez-le si c'est une erreur.",
  "The watched import folder is turned off. An admin can enable it.": "Le dossier d'importation surveillé est désactivé. Un administrateur peut l'activer.",
  "The watched import folder is turned off.": "Le dossier d'importation surveillé est désactivé.",
  "No transactions found in this OFX/QFX file.": "Aucune transaction trouvée dans ce fichier OFX/QFX.",
  "Could not recognise the date format in this QIF file.": "Format de date non reconnu dans ce fichier QIF.",

  // Single sign-on (routers/auth.py)
  "Password sign-in is turned off on this server. Use single sign-on.": "La connexion par mot de passe est désactivée sur ce serveur. Utilisez l'authentification unique.",

  // AI tools: categorizing and searching (routers/ai_tools.py, services/ai_tools.py)
  "AI isn't set up for your account. Choose a model in Settings.": "L'IA n'est pas configurée pour votre compte. Choisissez un modèle dans les paramètres.",
  "Turn on the AI assistant in Settings first. It's off until you choose to share data with the model.": "Activez d'abord l'assistant IA dans les paramètres. Il reste désactivé tant que vous n'acceptez pas de partager des données avec le modèle.",
  "Add some categories first.": "Ajoutez d'abord quelques catégories.",
  "That's a lot of AI requests in a short time. Try again in a few minutes.": "Cela fait beaucoup de requêtes à l'IA en peu de temps. Réessayez dans quelques minutes.",
  "That's a lot of AI searches in a short time. Try again in a few minutes.": "Cela fait beaucoup de recherches par IA en peu de temps. Réessayez dans quelques minutes.",
  "The model couldn't turn that into filters. Try naming a category, an amount or a time.": "Le modèle n'a pas pu transformer cela en filtres. Essayez de nommer une catégorie, un montant ou une période.",
  "The model's reply had an unexpected shape.": "La réponse du modèle avait une forme inattendue.",
  "The model server didn't return JSON.": "Le serveur du modèle n'a pas renvoyé de JSON.",
  "The model's answer wasn't valid JSON.": "La réponse du modèle n'était pas du JSON valide.",
  "The model's answer didn't contain a list of suggestions.": "La réponse du modèle ne contenait pas de liste de suggestions.",
  "The model's answer wasn't a set of filters.": "La réponse du modèle n'était pas un ensemble de filtres.",

  // Backups (routers/backups.py, services/backup.py)
  "Set a backup passphrase before turning backups on.": "Définissez une phrase de passe de sauvegarde avant d'activer les sauvegardes.",
  "Set a backup passphrase first.": "Définissez d'abord une phrase de passe de sauvegarde.",
  "A backup is already running.": "Une sauvegarde est déjà en cours.",
  "Backup not found": "Sauvegarde introuvable",

  // Investments (routers/investments.py, importers/holdings.py)
  "You already have this security.": "Vous avez déjà ce titre.",
  "Price not found": "Cours introuvable",
  "Fetching prices is turned off. An admin can enable it in Admin → Settings.": "La récupération des cours est désactivée. Un administrateur peut l'activer dans Administration → Paramètres.",
  "Pick a security or type its symbol.": "Choisissez un titre ou tapez son symbole.",
  "A buy or sell needs a quantity and a price or amount.": "Un achat ou une vente exige une quantité et un prix ou un montant.",
  "A split needs a ratio, e.g. 2 for a 2-for-1 split.": "Un fractionnement exige un ratio, par exemple 2 pour un fractionnement de 2 pour 1.",
  "Enter the amount.": "Entrez le montant.",
  "This file lists several accounts. Pick which one to import into this account.": "Ce fichier contient plusieurs comptes. Choisissez celui à importer dans ce compte.",
  "Use a CSV export. Excel files can be saved as CSV first.": "Utilisez une exportation CSV. Les fichiers Excel peuvent d'abord être enregistrés en CSV.",
  "Couldn't find a header row with Symbol and Quantity (holdings) or Date and Type (activity).": "Impossible de trouver une ligne d'en-tête avec Symbole et Quantité (titres) ou Date et Type (opérations).",
  "No positions found. The file needs Symbol and Quantity columns.": "Aucune position trouvée. Le fichier doit contenir les colonnes Symbole et Quantité.",
  "Could not find the date and type columns.": "Impossible de trouver les colonnes de date et de type.",
  "Could not recognise the date format.": "Format de date non reconnu.",

  // Debt planner (routers/planahead.py)
  "Only credit card and loan accounts are debts.": "Seuls les comptes de carte de crédit et de prêt sont des dettes.",
  "Only debts (liabilities) can be planned.": "Seules les dettes (passifs) peuvent être planifiées.",
  "Unknown debt": "Dette inconnue",

  // PDF statements (importers/__init__.py, importers/pdf.py); the checks with amounts are in lib/serverText.js
  "Unsupported file. Use OFX, QFX, QBO, QIF, CSV or a text-based PDF statement.": "Fichier non pris en charge. Utilisez OFX, QFX, QBO, QIF, CSV ou un relevé PDF contenant du texte.",
  "Could not read this PDF statement. QFX/OFX or CSV exports from your bank are safer when they are available.": "Impossible de lire ce relevé PDF. Les exportations QFX/OFX ou CSV de votre banque sont plus sûres lorsqu'elles sont offertes.",
  "No selectable text was found. Scanned/image-only PDF statements need OCR and cannot be imported yet. Download a CSV or QFX/OFX file from your bank instead.": "Aucun texte sélectionnable n'a été trouvé. Les relevés PDF numérisés (images seulement) exigent une reconnaissance de caractères et ne peuvent pas encore être importés. Téléchargez plutôt un fichier CSV ou QFX/OFX depuis le site de votre banque.",
  "FinVault could not make sense of this PDF's layout (PDF import is best-effort). Download a CSV or QFX/OFX export from your bank's website and import that instead.": "FinVault n'a pas pu interpréter la mise en page de ce PDF (l'importation PDF est approximative). Téléchargez plutôt une exportation CSV ou QFX/OFX depuis le site de votre banque et importez-la.",
  "No transactions were found in this PDF; its layout was not recognised (PDF import is best-effort). Try a QFX/OFX or CSV export from your bank instead, or a text-based statement PDF.": "Aucune transaction n'a été trouvée dans ce PDF; sa mise en page n'a pas été reconnue (l'importation PDF est approximative). Essayez plutôt une exportation QFX/OFX ou CSV de votre banque, ou un relevé PDF contenant du texte.",

  // Safe outbound addresses (services/sync.py); "<label> must …" is in lib/serverText.js
  "The return address must start with http:// or https://.": "L'adresse de retour doit commencer par http:// ou https://.",

  // Generic validation (pydantic)
  "Field required": "Champ obligatoire",

  // Password reset links (routers/account.py)
  "This member is turned off. Turn them back on first.": "Ce membre est désactivé. Réactivez-le d'abord.",
  "Password reset by email isn't set up on this server. Ask your household admin for a reset link.": "La réinitialisation du mot de passe par courriel n'est pas configurée sur ce serveur. Demandez un lien de réinitialisation à l'administrateur de votre foyer.",
  "Too many reset requests. Wait an hour and try again.": "Trop de demandes de réinitialisation. Attendez une heure et réessayez.",
  "This reset link is invalid, already used or expired. Ask for a new one.": "Ce lien de réinitialisation est invalide, déjà utilisé ou expiré. Demandez-en un nouveau.",
  "That two-factor code didn't work. Enter a current code from your authenticator app, or a recovery code.": "Ce code à deux facteurs n'a pas fonctionné. Entrez un code actuel de votre application d'authentification, ou un code de récupération.",
  // Tags, payees and budget rollover (routers/organize.py, routers/payees.py, services/tags.py, routers/categories.py)
  "A rule needs to set a category, a payee or a tag.": "Une règle doit définir une catégorie, un bénéficiaire ou une étiquette.",
  "Give the tag a name.": "Donnez un nom à l'étiquette.",
  "Tag not found.": "Étiquette introuvable.",
  "A tag with that name already exists. Merge the two instead.": "Une étiquette porte déjà ce nom. Fusionnez plutôt les deux.",
  "Pick the start month as year and month, like 2026-01.": "Indiquez le mois de départ en année et mois, comme 2026-01.",
  "Choose at least one payee.": "Choisissez au moins un bénéficiaire.",
  "Give the payee a name.": "Donnez un nom au bénéficiaire.",
}
