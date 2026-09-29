// Canadian French for password reset links (sign-in, reset page, Admin) and "Download all my data" (Settings).
// Keys are the exact English strings. Server messages for these features are in server.js.
export default {
  // Sign-in page and "Forgot password?"
  "Forgot password?": "Mot de passe oublié?",
  "Forgot your password?": "Vous avez oublié votre mot de passe?",
  "Enter the email you sign in with. We’ll send a link to choose a new password.": "Entrez le courriel avec lequel vous vous connectez. Nous vous enverrons un lien pour choisir un nouveau mot de passe.",
  "Send reset link": "Envoyer le lien de réinitialisation",
  "Check your email": "Vérifiez vos courriels",
  "If {email} has an account here, a link to choose a new password is on its way. It works once, for 1 hour.": "Si {email} a un compte ici, un lien pour choisir un nouveau mot de passe est en route. Il fonctionne une seule fois, pendant 1 heure.",
  "If {email} has an account here, a link to choose a new password is on its way. It works once, for {hours} hours.": "Si {email} a un compte ici, un lien pour choisir un nouveau mot de passe est en route. Il fonctionne une seule fois, pendant {hours} heures.",
  "Nothing after a few minutes? Check your spam folder, or ask your household admin for a reset link.": "Rien après quelques minutes? Vérifiez vos courriels indésirables, ou demandez un lien de réinitialisation à l'administrateur de votre foyer.",
  "This server can’t send reset emails. Ask your household admin: they can make you a one-time reset link from Admin, Members.": "Ce serveur ne peut pas envoyer de courriels de réinitialisation. Demandez à l'administrateur de votre foyer : il peut vous créer un lien de réinitialisation à usage unique dans Administration, Membres.",
  "This server uses single sign-on only, so there is no FinVault password to reset.": "Ce serveur utilise uniquement l'authentification unique; il n'y a donc aucun mot de passe FinVault à réinitialiser.",
  "Back to sign in": "Retour à la connexion",

  // Reset page
  "Choose a new password": "Choisissez un nouveau mot de passe",
  "For {email}. Once it’s changed, every device signed in to this account is signed out.": "Pour {email}. Une fois le mot de passe changé, tous les appareils connectés à ce compte sont déconnectés.",
  "New password again": "Nouveau mot de passe (confirmation)",
  "The two passwords don’t match yet.": "Les deux mots de passe ne correspondent pas encore.",
  "Two-factor code": "Code à deux facteurs",
  "This account uses two-factor login. Enter the 6-digit code from your authenticator app, or one of your recovery codes. Lost both? Ask your admin to reset two-factor first.": "Ce compte utilise la connexion à deux facteurs. Entrez le code à 6 chiffres de votre application d'authentification, ou l'un de vos codes de récupération. Vous avez perdu les deux? Demandez d'abord à votre administrateur de réinitialiser la connexion à deux facteurs.",
  "Checking the link…": "Vérification du lien…",
  "This link doesn’t work": "Ce lien ne fonctionne pas",
  "Ask your household admin for a new reset link, or use “Forgot password?” on the sign-in page if your server sends email.": "Demandez un nouveau lien de réinitialisation à l'administrateur de votre foyer, ou utilisez « Mot de passe oublié? » sur la page de connexion si votre serveur envoie des courriels.",
  "You were signed out everywhere. Sign in with your new password.": "Vous avez été déconnecté partout. Connectez-vous avec votre nouveau mot de passe.",
  "Back to FinVault": "Retour à FinVault",

  // Admin, Members
  "Reset password": "Réinitialiser le mot de passe",
  "Reset password for {email}": "Réinitialiser le mot de passe de {email}",
  "FinVault makes a one-time link where {name} chooses a new password. You never see or pick it. The link works for 24 hours, and making a new one cancels the old one.": "FinVault crée un lien à usage unique où {name} choisit un nouveau mot de passe. Vous ne le voyez jamais et ne le choisissez pas. Le lien fonctionne pendant 24 heures, et en créer un nouveau annule l'ancien.",
  "Their current password keeps working until they use the link. Using it signs them out on every device.": "Son mot de passe actuel fonctionne jusqu'à ce que le lien soit utilisé. L'utiliser le déconnecte de tous ses appareils.",
  "They have two-factor login on, so the reset page also asks for their authenticator or recovery code. If they lost those too, reset two-factor as well.": "La connexion à deux facteurs est activée pour ce membre; la page de réinitialisation demande donc aussi son code d'authentification ou de récupération. S'il les a perdus aussi, réinitialisez également la connexion à deux facteurs.",
  "Make reset link": "Créer le lien",
  "Give this link to {name} in person or in a message only they can read. Anyone with it can set the password.": "Donnez ce lien à {name} en personne ou dans un message que lui seul peut lire. Quiconque l'a peut définir le mot de passe.",
  "Reset link": "Lien de réinitialisation",
  "Works once, until {when}.": "Fonctionne une seule fois, jusqu'au {when}.",
  "Built from the address you opened FinVault at. Set PUBLIC_URL on the server if members use a different one.": "Construit à partir de l'adresse avec laquelle vous avez ouvert FinVault. Définissez PUBLIC_URL sur le serveur si les membres en utilisent une autre.",
  "Copy link": "Copier le lien",
  "Reset link copied": "Lien de réinitialisation copié",
  "Couldn’t copy. Select the link and copy it yourself.": "Impossible de copier. Sélectionnez le lien et copiez-le vous-même.",

  // Settings: your data
  "Your data": "Vos données",
  "Everything FinVault keeps for you, in one zip file you can open anywhere.": "Tout ce que FinVault conserve pour vous, dans un seul fichier zip que vous pouvez ouvrir n'importe où.",
  "A JSON file for each kind of record: accounts, transactions, splits, shared costs, categories, rules, budgets, bills, goals, assets, registered plans, investments, imports and your settings.": "Un fichier JSON pour chaque type de donnée : comptes, transactions, répartitions, dépenses partagées, catégories, règles, budgets, factures, objectifs, actifs, régimes enregistrés, placements, importations et vos paramètres.",
  "Your transactions as a CSV file, the same as the Transactions export.": "Vos transactions en fichier CSV, comme l'exportation de la page Transactions.",
  "Your receipt files, and a README that explains the format.": "Vos fichiers de reçus, et un fichier README qui explique le format.",
  "Only your own data is included. Your password, two-factor secrets and recovery codes, and saved API keys and bank-sync credentials are left out. The zip isn’t encrypted, so keep it somewhere safe.": "Seules vos propres données sont incluses. Votre mot de passe, vos secrets et codes de récupération à deux facteurs, ainsi que les clés d'API et identifiants de synchronisation bancaire enregistrés, sont exclus. Le fichier zip n'est pas chiffré : conservez-le en lieu sûr.",
  "Download all my data": "Télécharger toutes mes données",

  // Audit log event labels (services/password_reset.py)
  "Password reset link created by admin": "Lien de réinitialisation créé par l'administrateur",
  "Password reset email requested": "Courriel de réinitialisation demandé",
  "Password reset with a link": "Mot de passe réinitialisé avec un lien",
  "Password reset failed": "Échec de la réinitialisation du mot de passe",
  "Personal data downloaded": "Données personnelles téléchargées",
}
