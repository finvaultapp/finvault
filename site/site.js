// FinVault landing site: language, theme, the hero stage, the screenshot viewer and copy buttons.
(function () {
  'use strict'
  var root = document.documentElement
  var store = {
    get: function (k) { try { return localStorage.getItem(k) } catch (e) { return null } },
    set: function (k, v) { try { localStorage.setItem(k, v) } catch (e) {} },
  }
  var reduced = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches

  /* ---------- French (English lives in the HTML) ---------- */
  var FR = {
    'skip': 'Aller au contenu',
    'nav.features': 'Fonctions', 'nav.canada': 'Pensé pour le Canada', 'nav.look': 'Aperçu', 'nav.install': 'Installer', 'nav.code': 'Code',
    'theme': 'Passer au thème clair ou sombre', 'menu': 'Menu',
    'cta.host': 'L’héberger chez soi', 'cta.look': 'Voir l’application',
    'hero.eyebrow': 'Hébergé chez vous · Aucun mot de passe bancaire · Français et anglais',
    'hero.l1': 'Comptes. Cartes.', 'hero.l2': 'CELI. REER. CELIAPP.', 'hero.l3': 'Factures. Budgets.', 'hero.l4': 'Tout trié, chez vous.',
    'hero.lede': 'FinVault est une application privée de gestion d’argent pour votre ménage, qui tourne sur votre propre ordinateur ou serveur maison. Importez les relevés que votre banque vous donne déjà, classez chaque ligne en un clic et voyez où va l’argent.',
    'stage.label': 'Ce que FinVault vous montre',
    'stage.sort': 'À trier', 'stage.wall': 'Où va l’argent', 'stage.room': 'Droits de cotisation', 'stage.share': 'Partagé', 'stage.ask': 'Questions',
    'stage.foot': 'Illustration avec des chiffres inventés',
    'p.stamp': 'IMPORTÉ', 'p.filed': 'Classé dans Épicerie. Costco se triera tout seul la prochaine fois.', 'p.built': 'intégré', 'p.optocr': 'OCR facultatif', 'p.optprice': 'cours facultatifs', 'p.off': 'facultatif · désactivé',
    'f.ai.t': 'Interrogez vos données', 'f.ai.d': 'Questions en langage courant et suggestions de catégories, avec un modèle sur votre propre matériel ou votre propre compte OpenAI. Vous voyez d’abord ce qui serait envoyé.',
    'arch.n2.t': 'QFX · OFX · CSV · PDF texte',
    'p.month': 'Septembre 2026', 'p.spent': 'dépensés ce mois-ci', 'p.tosort': 'À trier', 'p.tosort.sub': 'Nouvelles lignes sans catégorie',
    'p.i1': '28 sept. · Visa remises', 'p.i2': '26 sept. · Visa remises', 'p.i3': '25 sept. · Compte courant',
    'cat.groceries': 'Épicerie', 'cat.shopping': 'Magasinage', 'cat.other': 'Autre…', 'cat.fuel': 'Essence', 'cat.settle': 'Remboursement', 'cat.income': 'Autres revenus', 'cat.dining': 'Restaurants', 'cat.subs': 'Abonnements',
    'p.wall.k': 'Où va l’argent', 'p.wall.sub': 'Chaque case se remplit vers sa limite mensuelle',
    'p.of900': 'sur 900 $', 'p.of260': 'sur 260 $', 'p.of350': 'sur 350 $ · dépassé', 'p.of40': 'sur 40 $',
    'p.room.k': 'Droits de cotisation · 2026', 'p.room.sub': 'de droits restants dans vos régimes',
    'p.tfsa': 'CELI', 'p.rrsp': 'REER', 'p.fhsa': 'CELIAPP', 'p.of7000': 'sur 7 000 $', 'p.of12000': 'sur 12 000 $', 'p.of8000': 'sur 8 000 $',
    'p.room.note': 'Copiez vos droits depuis Mon dossier de l’ARC. FinVault compte les dépôts.',
    'p.share.k': 'Partagé ce mois-ci', 'p.share.sub': 'avec 3 personnes · 11 dépenses',
    'p.owes1': 'vous doit 212,40 $', 'p.owes2': 'vous doit 96,15 $', 'p.owes3': 'vous lui devez 44,00 $',
    'p.share.note': 'Seule votre part compte dans les budgets et les rapports.',
    'p.ask.k': 'Interrogez vos propres données', 'p.ask.sub': 'Facultatif, et désactivé tant que vous ne l’activez pas',
    'p.q1': 'Combien avons-nous dépensé en épicerie cet été?', 'p.a1': '1 903,20 $ de juin à août, environ 12 % de plus qu’au printemps. La hausse vient surtout de juillet.',
    'p.q2': 'Restaurants de plus de 50 $ le mois dernier', 'p.a2': '4 transactions, 311,85 $ au total. Sushi Moto est la plus élevée, à 97,46 $.',
    'p.ask.note': 'Fonctionne avec le modèle de votre choix, y compris sur votre propre matériel. Vous voyez d’abord ce qui serait envoyé.',
    'banks.title': 'Compatible avec les fichiers que les banques canadiennes vous donnent déjà.',
    'banks.label': 'Banques avec des préréglages ou des formats de relevés testés', 'banks.cu': 'Caisses et coopératives', 'banks.pdf': 'PDF texte',
    'arch.title': 'Où vivent vos données',
    'arch.sub': 'FinVault ne communique jamais avec votre banque canadienne. Vous téléchargez un relevé, comme vous le pouvez déjà, et vous le rapportez chez vous. Rien d’autre ne passe.',
    'arch.n1.k': 'Votre banque', 'arch.n1.t': 'Services bancaires en ligne', 'arch.n1.d': 'Vous vous connectez sur le site de votre banque, comme d’habitude. Votre mot de passe n’en sort jamais.',
    'arch.l1': 'vous téléchargez', 'arch.n2.k': 'Un fichier de relevé', 'arch.n2.d': 'Un export ordinaire. Pas de clés, pas de jetons, pas de connexion permanente.',
    'arch.l2': 'vous importez', 'arch.n3.k': 'Votre serveur', 'arch.n3.t': 'FinVault + votre base de données', 'arch.n3.d': 'SQLite ou Postgres sur votre ordinateur, votre NAS ou votre serveur maison. Les sauvegardes sont chiffrées.',
    'arch.boundary': 'Jamais de mot de passe ni de connexion bancaire. Hors du Canada, la synchronisation bancaire facultative reste désactivée tant qu’un administrateur ne l’active pas.',
    'look.title': 'Des écrans calmes pour une routine mensuelle',
    'look.sub': 'Une fois par mois : téléchargez, importez, triez ce qui reste dans le bac. Environ deux minutes par compte.',
    'look.themes': 'Thème de la capture', 'look.light': 'Clair', 'look.dark': 'Sombre', 'look.screens': 'Écrans',
    'look.dash': 'Tableau de bord', 'look.import': 'Importer', 'look.tx': 'Transactions', 'look.reports': 'Rapports',
    'look.caption': 'De vrais écrans, remplis avec un ménage de démonstration fictif.',
    'feat.title': 'Tout ce dont un ménage a besoin, au même endroit',
    'feat.sub': 'Comptes, budgets, factures, dépenses partagées, placements et impôts. Rien ne quitte votre serveur à moins que vous ne l’activiez.',
    'g.bring': 'Importer et trier', 'g.plan': 'Planifier', 'g.look': 'Regarder en arrière', 'g.home': 'Votre ménage',
    'f.import.t': 'Import de relevés', 'f.import.d': 'QFX, OFX, QBO, QIF, CSV et PDF texte, avec préréglages bancaires. Les doublons sont ignorés et chaque import peut être annulé.',
    'f.move.t': 'Venir d’une autre application', 'f.move.d': 'Apportez votre historique de YNAB, Actual Budget, Mint ou Monarch d’un coup, avec les comptes, les catégories et les virements déjà jumelés.',
    'f.tags.t': 'Étiquettes et bénéficiaires', 'f.tags.d': 'Étiquetez un voyage ou des rénovations à travers les catégories, et regroupez les noms de marchands confus sous un seul bénéficiaire.',
    'f.export.t': 'Vos données, quand vous voulez', 'f.export.d': 'Téléchargez tout ce qui est à vous dans un seul zip, reçus compris. Un mot de passe oublié se règle avec un lien de réinitialisation à usage unique.',
    'f.sort.t': 'Tri en un clic', 'f.sort.d': 'Les nouvelles lignes attendent dans un bac avec les catégories probables. Les règles et les marchands mémorisés trient le reste.',
    'f.budget.t': 'Budgets', 'f.budget.d': 'Des limites mensuelles que vous voyez se remplir. Ce qui reste peut être reporté au mois suivant, comme des enveloppes.',
    'f.bills.t': 'Factures et rappels', 'f.bills.d': 'Les factures récurrentes jour par jour, des rappels avant chaque échéance et des alertes de hausse de prix ou de nouvel abonnement.',
    'f.room.t': 'CELI, REER et CELIAPP', 'f.room.d': 'Suivez vos cotisations par rapport aux droits que l’ARC vous accorde, pour éviter une cotisation excédentaire.',
    'f.tax.t': 'Période des impôts', 'f.tax.d': 'Frais médicaux, garde d’enfants, dons, déménagement et bureau à domicile, rassemblés au même endroit.',
    'f.share.t': 'Partages et dépenses communes', 'f.share.d': 'Répartissez une transaction entre catégories ou personnes, voyez qui doit quoi, et ne comptez que votre part.',
    'f.transfer.t': 'Virements jumelés', 'f.transfer.d': 'Payer une carte ou transférer vers l’épargne ne compte pas deux fois comme une dépense.',
    'f.receipt.t': 'Reçus', 'f.receipt.d': 'Joignez photos et PDF aux transactions. La lecture du texte, facultative, se fait sur votre propre serveur.',
    'f.invest.t': 'Placements', 'f.invest.d': 'Vos positions à partir des exports Wealthsimple et Questrade, avec gains, répartition et prix de base rajusté.',
    'f.fx.t': 'CAD et USD, honnêtement', 'f.fx.d': 'Conversion vers votre devise principale, avec un avertissement quand un taux manque plutôt qu’une estimation silencieuse.',
    'f.sec.t': 'Connexions séparées', 'f.sec.d': 'Chaque membre du ménage a ses propres données et sa connexion, avec double authentification, authentification unique et journal d’audit.',
    'feat.also': 'Aussi : objectifs d’épargne, actifs et valeur nette, prévision de trésorerie, plan de remboursement de dettes, bilan de l’année, dossier d’import surveillé, sauvegardes chiffrées et une application mobile installable.',
    'ca.title': 'Conçu pour la façon dont les ménages canadiens font affaire avec leur banque',
    'ca.sub': 'La plupart des applications veulent votre mot de passe bancaire. Les banques canadiennes déconseillent de le partager, et beaucoup de gens n’ont pas confiance. FinVault prend plutôt le fichier que votre banque offre déjà.',
    'ca.1.t': 'Aucune connexion aux banques canadiennes', 'ca.1.d': 'La synchronisation directe est bloquée pour les comptes canadiens, par conception. L’import est la seule porte d’entrée.',
    'ca.2.t': 'Français et anglais', 'ca.2.d': 'Toute l’application, y compris les catégories par défaut, en français canadien.',
    'ca.3.t': 'Régimes enregistrés et impôts', 'ca.3.d': 'Droits de CELI, REER et CELIAPP, plus les dépenses que votre comptable vous demande.',
    'ca.4.t': 'Hypothèques canadiennes', 'ca.4.d': 'Le planificateur de dettes utilise la capitalisation semestrielle, comme les hypothèques canadiennes.',
    'faq.title': 'Bon à savoir',
    'faq.1.q': 'Dois-je donner mon mot de passe bancaire à FinVault?', 'faq.1.a': 'Non. Vous téléchargez un relevé sur le site de votre banque et vous l’importez. FinVault ne demande jamais vos identifiants bancaires et ne se connecte jamais aux banques canadiennes.',
    'faq.2.q': 'Où mes données sont-elles stockées?', 'faq.2.a': 'Dans une base de données sur la machine où vous l’installez : un portable, un NAS ou un serveur maison. Il n’y a pas de nuage FinVault.',
    'faq.3.q': 'Mon ou ma partenaire peut-il aussi l’utiliser?', 'faq.3.a': 'Oui. Chaque personne a sa propre connexion et ses données, et vous pouvez partager des dépenses. Une personne est l’administrateur qui invite les autres.',
    'faq.5.q': 'J’arrive de Mint, YNAB ou d’une autre application. Puis-je apporter mon historique?', 'faq.5.a': 'Oui. Exportez depuis YNAB, Actual Budget, Mint ou Monarch et utilisez « Venir d’une autre application ». Les comptes et catégories sont associés, les virements jumelés, les libellés deviennent des étiquettes, ce qui est déjà importé est ignoré, et tout peut être annulé.',
    'faq.4.q': 'Dois-je utiliser l’IA?', 'faq.4.a': 'Non. Les fonctions d’IA sont désactivées par défaut. Si vous les voulez, vous pouvez utiliser un modèle sur votre propre matériel ou brancher votre propre compte OpenAI.',
    'inst.title': 'En marche en quelques minutes', 'inst.sub': 'Il vous faut Docker. Trois étapes, puis ouvrez-la dans votre navigateur.',
    'inst.1': 'Obtenir le code', 'inst.2': 'Le configurer', 'inst.3': 'Le démarrer', 'copy': 'Copier',
    'inst.foot': 'Le premier compte créé devient l’administrateur. Vos données vivent dans le volume Docker finvault-data.',
    'foot.tag': 'Vos relevés. Votre serveur. Votre ménage.', 'foot.built': 'Conçu avec', 'foot.nav': 'Pied de page',
  }
  var ALT = {
    en: {
      dashboard: 'The FinVault dashboard: a To sort tray of new transactions beside category pockets that fill toward their monthly limits.',
      import: 'The import screen: choose an account, drop a statement file, and follow bank-specific download steps.',
      transactions: 'The transactions list with search, filters and categories, and money in and out in separate colours.',
      reports: 'Reports: income, expenses, net saved and savings rate, with a month-by-month chart and top categories.',
    },
    fr: {
      dashboard: 'Le tableau de bord FinVault : un bac « À trier » de nouvelles transactions à côté des cases de catégories qui se remplissent vers leur limite mensuelle.',
      import: 'L’écran d’import : choisissez un compte, déposez un relevé et suivez les étapes propres à votre banque.',
      transactions: 'La liste des transactions avec recherche, filtres et catégories, entrées et sorties en couleurs distinctes.',
      reports: 'Rapports : revenus, dépenses, épargne nette et taux d’épargne, avec un graphique mois par mois et les principales catégories.',
    },
  }
  var copyDone = { en: 'Copied', fr: 'Copié' }

  // Money in the illustration follows the language: $2,408.61 or 2 408,61 $.
  function formatMoney() {
    document.querySelectorAll('.money').forEach(function (el) {
      var v = parseFloat(el.dataset.v), d = el.dataset.d ? +el.dataset.d : 2
      var text = new Intl.NumberFormat(lang === 'fr' ? 'fr-CA' : 'en-CA', { style: 'currency', currency: 'CAD', minimumFractionDigits: d, maximumFractionDigits: d }).format(Math.abs(v))
      if (el.hasAttribute('data-signed')) text = (v < 0 ? '−' : '+') + text
      el.textContent = text
    })
  }

  var EN = {}
  document.querySelectorAll('[data-i18n]').forEach(function (el) { EN[el.dataset.i18n] = el.textContent })
  document.querySelectorAll('[data-i18n-label]').forEach(function (el) { EN[el.dataset.i18nLabel] = el.getAttribute('aria-label') })
  var lang = 'en'

  function setLang(next) {
    lang = next === 'fr' ? 'fr' : 'en'
    var dict = lang === 'fr' ? FR : EN
    root.lang = lang === 'fr' ? 'fr-CA' : 'en'
    document.querySelectorAll('[data-i18n]').forEach(function (el) {
      var v = dict[el.dataset.i18n]; if (v != null) el.textContent = v
    })
    document.querySelectorAll('[data-i18n-label]').forEach(function (el) {
      var v = dict[el.dataset.i18nLabel]; if (v != null) el.setAttribute('aria-label', v)
    })
    document.querySelectorAll('[data-lang]').forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.lang === lang)) })
    shot.alt = ALT[lang][current.shot]
    formatMoney()
    store.set('fv.site.lang', lang)
  }
  document.querySelectorAll('[data-lang]').forEach(function (b) {
    b.addEventListener('click', function () { setLang(b.dataset.lang) })
  })

  /* ---------- Site theme ---------- */
  function isDark() {
    var t = root.dataset.theme
    if (t) return t === 'dark'
    return window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches
  }
  document.getElementById('theme').addEventListener('click', function () {
    var next = isDark() ? 'light' : 'dark'
    root.dataset.theme = next
    store.set('fv.site.theme', next)
    setShotTheme(next)
  })

  /* ---------- Tabs helper (arrow keys, roving tabindex) ---------- */
  function tablist(list, onSelect) {
    var tabs = Array.prototype.slice.call(list.querySelectorAll('[role="tab"]'))
    function select(i, focus) {
      tabs.forEach(function (t, j) {
        t.setAttribute('aria-selected', String(i === j))
        t.tabIndex = i === j ? 0 : -1
      })
      if (focus) tabs[i].focus()
      onSelect(tabs[i], i)
    }
    tabs.forEach(function (t, i) {
      t.addEventListener('click', function () { select(i, false) })
      t.addEventListener('keydown', function (e) {
        var k = e.key, n = tabs.length
        if (k === 'ArrowRight' || k === 'ArrowLeft' || k === 'Home' || k === 'End') {
          e.preventDefault()
          var to = k === 'Home' ? 0 : k === 'End' ? n - 1 : (i + (k === 'ArrowRight' ? 1 : -1) + n) % n
          select(to, true)
        }
      })
    })
    return { select: select, count: tabs.length }
  }

  /* ---------- Hero stage ---------- */
  var stage = document.querySelector('.stage')
  var index = 0, timer = null, DWELL = 6000
  stage.style.setProperty('--dwell', DWELL + 'ms')
  var tabRow = stage.querySelector('.stage-tabs')
  var stageTabs = tablist(tabRow, function (tab, i) {
    index = i
    stage.querySelectorAll('[role="tabpanel"]').forEach(function (p) { p.hidden = p.id !== tab.getAttribute('aria-controls') })
    tabRow.scrollTo({ left: Math.max(0, tab.offsetLeft - 24), behavior: reduced ? 'auto' : 'smooth' })
    if (tab.id === 't-sort') playSort()
    schedule()
  })
  function edge() { tabRow.classList.toggle('at-end', tabRow.scrollLeft + tabRow.clientWidth >= tabRow.scrollWidth - 4) }
  tabRow.addEventListener('scroll', edge, { passive: true }); edge()

  // The one authored motion: pick the likely chip, the line leaves the tray, the count drops.
  var sortTimers = []
  function playSort() {
    var row = document.getElementById('sort-me'), chip = document.getElementById('sort-chip')
    var count = document.getElementById('sort-count'), note = document.getElementById('sort-note')
    sortTimers.forEach(clearTimeout); sortTimers = []
    row.classList.remove('sorted'); chip.classList.remove('picked'); note.classList.remove('show'); count.textContent = '3'
    if (reduced) return
    sortTimers.push(setTimeout(function () { chip.classList.add('picked') }, 1400))
    sortTimers.push(setTimeout(function () { row.classList.add('sorted'); count.textContent = '2'; note.classList.add('show') }, 2100))
  }
  function schedule() {
    clearTimeout(timer)
    if (reduced || stage.classList.contains('paused') || stage.classList.contains('still')) return
    timer = setTimeout(function () { stageTabs.select((index + 1) % stageTabs.count, false) }, DWELL)
  }
  if (reduced) stage.classList.add('still')
  // Any direct interaction stops the rotation for good; hover or focus pauses it.
  stage.querySelector('.stage-tabs').addEventListener('click', function () { stage.classList.add('still'); clearTimeout(timer) })
  stage.querySelector('.stage-tabs').addEventListener('keydown', function () { stage.classList.add('still'); clearTimeout(timer) })
  stage.addEventListener('mouseenter', function () { stage.classList.add('paused'); clearTimeout(timer) })
  stage.addEventListener('mouseleave', function () { stage.classList.remove('paused'); schedule() })
  stage.addEventListener('focusin', function () { stage.classList.add('paused'); clearTimeout(timer) })
  stage.addEventListener('focusout', function () { stage.classList.remove('paused'); schedule() })
  document.addEventListener('visibilitychange', function () { if (document.hidden) clearTimeout(timer); else schedule() })
  playSort()
  schedule()

  /* ---------- Screenshot viewer ---------- */
  var shot = document.getElementById('shot'), shotSm = document.getElementById('shot-sm')
  var phoneMq = window.matchMedia('(max-width: 640px)')
  var current = { shot: 'dashboard', theme: isDark() ? 'dark' : 'light' }
  function showShot() {
    var dark = current.theme === 'dark' ? '-dark' : ''
    var src = 'assets/' + current.shot + dark + '.jpg'
    var srcSm = 'assets/' + current.shot + '-phone' + dark + '.jpg'
    if (shot.getAttribute('src') === src && shotSm.getAttribute('srcset') === srcSm) return
    shot.classList.add('swap')
    var img = new Image()
    img.onload = img.onerror = function () {
      shotSm.srcset = srcSm; shot.src = src; shot.alt = ALT[lang][current.shot]; shot.classList.remove('swap')
    }
    img.src = phoneMq.matches ? srcSm : src
  }
  function setShotTheme(t) {
    current.theme = t
    document.querySelectorAll('[data-shot-theme]').forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.shotTheme === t)) })
    showShot()
  }
  tablist(document.querySelector('.shot-tabs'), function (tab) { current.shot = tab.dataset.shot; showShot() })
  document.querySelectorAll('[data-shot-theme]').forEach(function (b) {
    b.addEventListener('click', function () { setShotTheme(b.dataset.shotTheme) })
  })
  setShotTheme(current.theme)

  /* ---------- Phone and tablet menu ---------- */
  var menuBtn = document.getElementById('menu-btn'), menu = document.getElementById('menu')
  function setMenu(open, focusBack) {
    menu.hidden = !open
    menuBtn.setAttribute('aria-expanded', String(open))
    if (open) menu.querySelector('a').focus()
    else if (focusBack) menuBtn.focus()
  }
  menuBtn.addEventListener('click', function () { setMenu(menu.hidden, false) })
  menu.addEventListener('click', function (e) { if (e.target.closest('a')) setMenu(false, false) })
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !menu.hidden) setMenu(false, true) })
  document.addEventListener('click', function (e) { if (!menu.hidden && !e.target.closest('.top')) setMenu(false, false) })
  window.matchMedia('(min-width: 1081px)').addEventListener('change', function (e) { if (e.matches) setMenu(false, false) })

  /* ---------- Copy buttons ---------- */
  document.querySelectorAll('.copy').forEach(function (b) {
    b.addEventListener('click', function () {
      var text = b.parentElement.querySelector('code').textContent
        .split('\n').filter(function (l) { return l.trim() && l.trim()[0] !== '#' }).join('\n')
      var done = function () {
        b.textContent = copyDone[lang]; b.classList.add('done')
        setTimeout(function () { b.textContent = lang === 'fr' ? FR.copy : EN.copy; b.classList.remove('done') }, 1600)
      }
      if (navigator.clipboard) navigator.clipboard.writeText(text).then(done, function () {})
    })
  })

  /* ---------- Header border and reveal on scroll ---------- */
  var top = document.querySelector('.top')
  var onScroll = function () { top.classList.toggle('scrolled', window.scrollY > 8) }
  window.addEventListener('scroll', onScroll, { passive: true }); onScroll()

  if ('IntersectionObserver' in window && !reduced) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add('seen'); io.unobserve(e.target) } })
    }, { rootMargin: '0px 0px -8% 0px' })
    document.querySelectorAll('.section > *, .banks .wrap > *, .canada-grid > *, .case .cell, .steps li').forEach(function (el) {
      if (el.getBoundingClientRect().top > window.innerHeight) { el.classList.add('reveal'); io.observe(el) }
    })
  }

  /* ---------- Starting language ---------- */
  var saved = store.get('fv.site.lang')
  var start = saved || ((navigator.language || '').toLowerCase().indexOf('fr') === 0 ? 'fr' : 'en')
  if (start === 'fr') setLang('fr')
})()
