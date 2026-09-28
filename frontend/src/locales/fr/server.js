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

  // Generic validation (pydantic)
  "Field required": "Champ obligatoire",
}
