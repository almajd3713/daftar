# Labelling guide · Guide d'étiquetage · دليل الوسم

[English](#english) · [Français](#français) · [العربية](#العربية)

---

## English

### What this is for

You describe what a workbook really contains. Daftar is then scored by comparing what it understood with your description. **Record what is true, not what Daftar can do**: if it's wrong, its score should drop.

Label only workbooks whose language you can read. Leave the others for someone who can.

### Starting

```sh
uv run daftar label --labels eval/labels --who "Your name"
```

Open <http://127.0.0.1:8790>. Everything saves by itself. Time is counted while you're working, and it stays on your machine.

If the project runs on another machine, open a tunnel first: `ssh -L 8790:127.0.0.1:8790 machine`.

**dev** workbooks open with Daftar's guesses for you to correct. **test** workbooks open blank: they produce the published number, and a guess would sway your judgement.

### For each sheet

1. **Choose the sheet's kind** (see the table).
2. **Mark each table.** Select it and press `T`. A table includes its header rows and total rows.
3. **Mark header rows** (`H`) **and total rows** (`O`). A header on two rows is two header rows.
4. **Give each column a type.** Names come from the headers. Don't retype them: they aren't scored.
5. **Mark the title and notes** (`1`, `2`). They stay outside the table.

Then, for the workbook: the **relations** between sheets, the **series** of tabs, and **Mark reviewed**.

| Key | Action |
|---|---|
| `T` | New table |
| `R` | The active table takes the selection |
| `H` / `O` | Header row / total row |
| `1` `2` `3` `4` | Title, notes, inputs, outputs |
| `L` | Relation: press on the column it starts from, then on the column it points to |
| `Ctrl+Z` | Undo |

### Sheet kind

| Kind | When | Example |
|---|---|---|
| `register` | One row = one thing | customers, students, contracts |
| `ledger` | One row = one dated money movement | sales, payments, expenses |
| `tracker` | One row = one job moving through statuses | repairs, case files |
| `formulaModel` | You fill in cells and others work out the answer. It isn't a list | a quote, a pay calculation |
| `referenceList` | A short list other sheets use | prices, codes, categories |
| `notConverted` | Not data for the app. Give the reason | see below |

Reasons for `notConverted`:

- `form`: something to fill in or print (an order form, a blank invoice).
- `report`: a summary worked out from other sheets (a recap, a dashboard).
- `chartOrPivotOnly`: only a chart or a pivot table.
- `empty`: empty.
- `outOfScope`: anything else (instructions, notes, scrap work).

**Unsure between `ledger` and `register`?** Look for a date and an amount on each row. If they say what happened that day, it's `ledger`.

**Unsure between `referenceList` and `register`?** Does another sheet use it to look up values? If not, it's `register`.

### Column type

| Type | When |
|---|---|
| `computed` | A formula copied down the column (blue text). **It beats every other type**, even when the result is an amount or a name |
| `link` | The values point to a key on another sheet. Add the relation too (`L`) |
| `choice` | A few repeating values picked from a list: status, category |
| `multichoice` | Several of those values in one cell |
| `money` | An amount of money |
| `percent` | A percentage |
| `integer` / `decimal` | A whole / decimal number that isn't money. A running receipt number stays `integer` |
| `date` / `datetime` | A date / a date with a time |
| `boolean` | Yes or no, two states only |
| `phone` / `email` | A phone number / an email address. A phone number is `phone` even when stored as a number |
| `longtext` | Sentences, remarks |
| `text` | Everything else: names, codes, addresses |

A mixed column takes the type of most of its values. Say so in the notes if it matters.

### Relations

A relation goes from the column that **points** (many rows) to the column that **identifies** (one row per value). For example `January!C` → `Customers!A`.

Count a lookup (`VLOOKUP`), a dropdown fed by another sheet, or values that clearly match. On a series of tabs, add the relation **for each tab**.

### Series of tabs

Monthly or yearly tabs holding the same table get the same name under "Part of a series of tabs". A recap isn't part of the series, and neither is a tab with a different layout.

### Hard cases

- **Several tables on a sheet:** one table per block, separate, with no overlap.
- **A blank row inside a table:** it stays in the table if the same columns carry on after it.
- **A total far from the table**, after blank rows: it stays outside.
- **Subtotals in the middle:** they're total rows.
- **An empty column in a table:** leave it as `text`.
- **Formulas or a chart to check:** "Open the original" opens the real file. Clicking a cell shows its formula and format at the bottom of the screen.

**Still unsure?** Decide, then explain in **Notes**. A recorded decision beats getting stuck, and those notes improve this guide.

### Finishing

**Mark reviewed** checks the workbook. Red errors block it; orange ones only ask for a second look. If you change a workbook afterwards it goes back to draft, so mark it again.

---

## Français

### À quoi ça sert

Vous décrivez ce que contient vraiment un classeur. Daftar est ensuite noté en comparant ce qu'il a compris à votre description. **Notez ce qui est vrai, pas ce que Daftar sait faire** : s'il se trompe, sa note doit baisser.

### Démarrer

```sh
uv run daftar label --labels eval/labels --who "Votre nom"
```

Ouvrez <http://127.0.0.1:8790>. Tout s'enregistre seul. Le temps passé est compté pendant que vous travaillez, et il reste sur votre machine.

Si le projet tourne sur une autre machine, ouvrez d'abord un tunnel : `ssh -L 8790:127.0.0.1:8790 machine`.

Les classeurs du jeu **dev** s'ouvrent avec les propositions de Daftar, à corriger. Ceux du jeu **test** s'ouvrent vides : ils servent au chiffre publié, et une proposition influencerait votre jugement.

### Pour chaque feuille

1. **Choisissez le type de la feuille** (voir le tableau).
2. **Délimitez chaque tableau.** Sélectionnez-le puis appuyez sur `T`. Il comprend ses lignes d'en-tête et ses lignes de total.
3. **Marquez les lignes d'en-tête** (`H`) et **de total** (`O`). Un en-tête sur deux lignes, ce sont deux lignes d'en-tête.
4. **Donnez son type à chaque colonne.** Les noms viennent des en-têtes : ne les retapez pas, ils ne sont pas notés.
5. **Marquez le titre et les notes** (`1`, `2`) : ils restent hors du tableau.

Puis, pour le classeur : les **liens** entre feuilles, les **séries** d'onglets, et **Mark reviewed**.

| Touche | Action |
|---|---|
| `T` | Nouveau tableau |
| `R` | Le tableau actif prend la sélection |
| `H` / `O` | Ligne d'en-tête / de total |
| `1` `2` `3` `4` | Titre, notes, entrées, résultats |
| `L` | Lien : à presser sur la colonne de départ, puis sur celle d'arrivée |
| `Ctrl+Z` | Annuler |

### Type de la feuille

| Type | Quand le choisir | Exemple |
|---|---|---|
| `register` | Une ligne = une chose | clients, élèves, contrats |
| `ledger` | Une ligne = un mouvement d'argent daté | ventes, paiements, dépenses |
| `tracker` | Une ligne = un travail qui passe par des états | réparations, dossiers |
| `formulaModel` | On remplit des cases et d'autres calculent le résultat. Ce n'est pas une liste | devis, calcul de salaire |
| `referenceList` | Petite liste qui sert aux autres feuilles | tarifs, codes, catégories |
| `notConverted` | Pas de données pour l'application. Indiquez la raison | voir ci-dessous |

Raisons pour `notConverted` :

- `form` : un formulaire à remplir ou à imprimer (bon de commande, facture vierge).
- `report` : un résumé calculé à partir d'autres feuilles (bilan, tableau de bord).
- `chartOrPivotOnly` : seulement un graphique ou un tableau croisé.
- `empty` : vide.
- `outOfScope` : le reste (consignes, notes, brouillon).

**En cas de doute entre `ledger` et `register` :** cherchez une date et un montant sur chaque ligne. S'ils décrivent ce qui s'est passé ce jour-là, c'est `ledger`.

**En cas de doute entre `referenceList` et `register` :** une autre feuille s'en sert-elle pour retrouver ses valeurs ? Si non, c'est `register`.

### Type des colonnes

| Type | Quand le choisir |
|---|---|
| `computed` | Une formule recopiée sur la colonne (texte bleu). **Passe avant tous les autres**, même si le résultat est un montant ou un nom |
| `link` | Les valeurs renvoient à une clé d'une autre feuille. Ajoutez aussi le lien (`L`) |
| `choice` | Quelques valeurs qui reviennent, choisies dans une liste : statut, catégorie |
| `multichoice` | Plusieurs de ces valeurs dans une même case |
| `money` | Une somme d'argent |
| `percent` | Un pourcentage |
| `integer` / `decimal` | Un nombre entier / à virgule qui n'est pas de l'argent. Un numéro de bon qui se suit reste `integer` |
| `date` / `datetime` | Une date / une date avec l'heure |
| `boolean` | Oui ou non, deux états seulement |
| `phone` / `email` | Un téléphone / une adresse e-mail. Un téléphone est `phone` même écrit comme un nombre |
| `longtext` | Des phrases, des remarques |
| `text` | Le reste : noms, codes, adresses |

Une colonne mélangée prend le type de la majorité de ses valeurs. Mentionnez-le dans les notes si c'est gênant.

### Liens

Un lien part de la colonne qui **renvoie** (les nombreuses lignes) et arrive à la colonne qui **identifie** (une ligne par valeur). Exemple : `Janvier!C` → `Clients!A`.

Comptez comme lien une recherche (`VLOOKUP`), une liste déroulante alimentée par une autre feuille, ou des valeurs qui correspondent clairement. Sur une série d'onglets, ajoutez le lien **pour chaque onglet**.

### Séries d'onglets

Des onglets mensuels ou annuels qui contiennent le même tableau reçoivent le même nom dans « Part of a series of tabs ». Un récapitulatif n'en fait pas partie, ni un onglet de structure différente.

### Cas difficiles

- **Plusieurs tableaux sur une feuille :** faites un tableau par bloc, séparés, sans chevauchement.
- **Une ligne vide au milieu d'un tableau :** elle reste dans le tableau, si la suite continue les mêmes colonnes.
- **Un total éloigné du tableau**, après des lignes vides : il reste hors du tableau.
- **Sous-totaux au milieu :** ce sont des lignes de total.
- **Une colonne vide dans un tableau :** laissez-la de type `text`.
- **Des formules ou un graphique à vérifier :** « Open the original » ouvre le vrai fichier. Un clic sur une case montre sa formule et son format en bas de l'écran.

**Vous hésitez encore ?** Décidez, puis expliquez dans **Notes**. Une décision notée vaut mieux qu'un blocage, et ces notes servent à améliorer ce guide.

### Terminer

**Mark reviewed** vérifie le classeur. Les erreurs en rouge bloquent ; celles en orange demandent seulement un second regard. Si vous modifiez un classeur ensuite, il repasse en brouillon : marquez-le de nouveau.

---

<div dir="rtl">

## العربية

### الهدف

تصف ما يحتويه المصنف فعلا. بعد ذلك يُقيَّم Daftar بمقارنة ما فهمه بوصفك. **سجّل ما هو صحيح، لا ما يستطيع Daftar فعله**: إذا أخطأ، يجب أن تنخفض نتيجته.

### البدء

<div dir="ltr">

```sh
uv run daftar label --labels eval/labels --who "Votre nom"
```

</div>

افتح <span dir="ltr">`http://127.0.0.1:8790`</span>. يُحفظ كل شيء تلقائيا. يُحسب الوقت أثناء عملك فقط، ويبقى على جهازك.

إذا كان المشروع يعمل على جهاز آخر، افتح نفقا أولا: <span dir="ltr">`ssh -L 8790:127.0.0.1:8790 machine`</span>.

مصنفات مجموعة **dev** تُفتح ومعها اقتراحات Daftar لتصحيحها. أما مصنفات مجموعة **test** فتُفتح فارغة: فهي أساس الرقم المنشور، وأي اقتراح قد يؤثر في حكمك.

### لكل ورقة

1. **اختر نوع الورقة** (انظر الجدول).
2. **حدّد كل جدول.** حدّده ثم اضغط `T`. يشمل الجدول صفوف العناوين وصفوف المجموع.
3. **علّم صفوف العناوين** (`H`) **وصفوف المجموع** (`O`). العنوان الممتد على صفين يعني صفَّي عناوين.
4. **حدّد نوع كل عمود.** الأسماء تأتي من العناوين، فلا تُعد كتابتها: لا تدخل في التقييم.
5. **علّم العنوان والملاحظات** (`1`، `2`): تبقى خارج الجدول.

ثم على مستوى المصنف: **الروابط** بين الأوراق، و**سلاسل** الأوراق، ثم **Mark reviewed**.

| المفتاح | العملية |
|---|---|
| `T` | جدول جديد |
| `R` | يأخذ الجدول النشط التحديد الحالي |
| `H` / `O` | صف عناوين / صف مجموع |
| `1` `2` `3` `4` | عنوان، ملاحظات، مدخلات، نتائج |
| `L` | رابط: اضغطه على عمود البداية ثم على عمود الوصول |
| `Ctrl+Z` | تراجع |

### نوع الورقة

| النوع | متى تختاره | مثال |
|---|---|---|
| `register` | الصف الواحد = شيء واحد | زبائن، تلاميذ، عقود |
| `ledger` | الصف الواحد = حركة مالية مؤرخة | مبيعات، مدفوعات، مصاريف |
| `tracker` | الصف الواحد = عمل يمر بحالات | تصليحات، ملفات |
| `formulaModel` | تملأ خانات وتحسب خانات أخرى النتيجة. ليست قائمة | تسعيرة، حساب أجرة |
| `referenceList` | قائمة صغيرة تستعملها الأوراق الأخرى | أسعار، رموز، أصناف |
| `notConverted` | ليست بيانات للتطبيق. اذكر السبب | انظر أدناه |

أسباب `notConverted`:

- `form`: استمارة للملء أو الطباعة (وصل طلب، فاتورة فارغة).
- `report`: ملخص محسوب من أوراق أخرى (حصيلة، لوحة متابعة).
- `chartOrPivotOnly`: رسم بياني أو جدول محوري فقط.
- `empty`: فارغة.
- `outOfScope`: الباقي (تعليمات، ملاحظات، مسودة).

**عند التردد بين `ledger` و`register`:** ابحث عن تاريخ ومبلغ في كل صف. إذا كانا يصفان ما حدث في ذلك اليوم فهي `ledger`.

**عند التردد بين `referenceList` و`register`:** هل تستعملها ورقة أخرى لجلب قيمها؟ إذا لم يكن كذلك فهي `register`.

### نوع الأعمدة

| النوع | متى تختاره |
|---|---|
| `computed` | صيغة منسوخة على طول العمود (نص أزرق). **له الأولوية على كل الأنواع**، حتى لو كانت النتيجة مبلغا أو اسما |
| `link` | القيم تشير إلى مفتاح في ورقة أخرى. أضف الرابط أيضا (`L`) |
| `choice` | قيم قليلة متكررة تُختار من قائمة: حالة، صنف |
| `multichoice` | عدة قيم من هذا النوع في خانة واحدة |
| `money` | مبلغ مالي |
| `percent` | نسبة مئوية |
| `integer` / `decimal` | عدد صحيح / عشري ليس مالا. رقم الوصل المتسلسل يبقى `integer` |
| `date` / `datetime` | تاريخ / تاريخ مع الوقت |
| `boolean` | نعم أو لا، حالتان فقط |
| `phone` / `email` | هاتف / بريد إلكتروني. الهاتف يبقى `phone` حتى لو كُتب كعدد |
| `longtext` | جمل وملاحظات |
| `text` | الباقي: أسماء، رموز، عناوين |

العمود المختلط يأخذ نوع أغلب قيمه. اذكر ذلك في الملاحظات إذا كان مزعجا.

### الروابط

يبدأ الرابط من العمود الذي **يشير** (الصفوف الكثيرة) وينتهي عند العمود الذي **يعرّف** (صف واحد لكل قيمة). مثال: <span dir="ltr">`Janvier!C` → `Clients!A`</span>.

اعتبر رابطا كل بحث (`VLOOKUP`)، أو قائمة منسدلة تغذيها ورقة أخرى، أو قيما تتطابق بوضوح. في سلسلة أوراق، أضف الرابط **لكل ورقة**.

### سلاسل الأوراق

الأوراق الشهرية أو السنوية التي تحتوي الجدول نفسه تأخذ الاسم نفسه في خانة «Part of a series of tabs». الملخص ليس منها، ولا الورقة ذات البنية المختلفة.

### حالات صعبة

- **عدة جداول في ورقة واحدة:** جدول لكل كتلة، منفصلة ودون تداخل.
- **صف فارغ وسط جدول:** يبقى داخل الجدول إذا استمرت الأعمدة نفسها بعده.
- **مجموع بعيد عن الجدول** بعد صفوف فارغة: يبقى خارج الجدول.
- **مجاميع فرعية في الوسط:** هي صفوف مجموع.
- **عمود فارغ داخل جدول:** اتركه من نوع `text`.
- **صيغ أو رسم بياني للتحقق:** «Open the original» يفتح الملف الحقيقي. النقر على خانة يعرض صيغتها وتنسيقها أسفل الشاشة.

**ما زلت مترددا؟** قرّر، ثم اشرح في **Notes**. القرار المكتوب أفضل من التوقف، وهذه الملاحظات تساعد على تحسين هذا الدليل.

### الإنهاء

**Mark reviewed** يتحقق من المصنف. الأخطاء بالأحمر تمنع الإنهاء، والتي بالبرتقالي تطلب مراجعة ثانية فقط. إذا عدّلت مصنفا بعد ذلك يعود مسودة: علّمه من جديد.

</div>
