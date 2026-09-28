import {
  Banknote, BadgePercent, Bus, Car, CircleHelp, CreditCard, Film, Fuel, Gift, GraduationCap, HeartPulse, Home,
  Landmark, Lightbulb, Plane, Receipt, Repeat, ShieldCheck, ShoppingBag, ShoppingCart, Smartphone, Sparkles,
  TrendingUp, Utensils, Users, ArrowLeftRight, PiggyBank, Wallet, Baby, Dumbbell, PawPrint,
} from 'lucide-react'

const RULES = [
  [/salary|payroll|wage|pay\b/i, Banknote], [/interest|dividend|invest/i, TrendingUp], [/income/i, Wallet],
  [/grocer|supermarket/i, ShoppingCart], [/dining|restaurant|food|coffee/i, Utensils], [/rent|mortgage|housing|home/i, Home],
  [/utilit|hydro|electric|water|gas bill/i, Lightbulb], [/phone|internet|mobile/i, Smartphone], [/transport|transit|bus/i, Bus],
  [/fuel|gas/i, Fuel], [/car|auto|vehicle/i, Car], [/insur/i, ShieldCheck], [/health|medical|pharma|dental/i, HeartPulse],
  [/shop|cloth|amazon/i, ShoppingBag], [/subscri|stream/i, Repeat], [/entertain|movie|fun/i, Film], [/travel|flight|hotel/i, Plane],
  [/kid|child|family|baby/i, Baby], [/gift|donat|charit/i, Gift], [/fee|charge/i, BadgePercent], [/tax/i, Landmark],
  [/transfer/i, ArrowLeftRight], [/credit card/i, CreditCard], [/educat|school|tuition/i, GraduationCap],
  [/saving/i, PiggyBank], [/gym|fitness|sport/i, Dumbbell], [/pet/i, PawPrint], [/bill/i, Receipt], [/people|friend/i, Users],
  [/other/i, Sparkles],
]

export function categoryIcon(name) {
  if (!name) return CircleHelp
  for (const [re, Icon] of RULES) if (re.test(name)) return Icon
  return Sparkles
}
