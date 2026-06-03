# -*- coding: utf-8 -*-
"""
Fills the 'Hi France Master' Google Sheet with 15 unique French 5-star reviews
for each of the 30 listed Belgian locksmith/glazier/plumber businesses.
"""
import sys, time
sys.path.insert(0, r"C:\Users\nisha\OneDrive\Desktop\sofian")
from gsheet_api import GSheet

SHEET_ID = "1GwKc-8O-1dYbLsjItxm6cgQrbLmb9XVWEAEyX5zGJ-Y"

# Each tab name -> list of 15 unique French 5-star reviews.
# All reviews follow the french-review skill ruleset (varied openings,
# specific service details, varied endings, no exclamation marks, etc.)
REVIEWS = {

# =========================================================================
# 1. Serrurier Bruxelles - SVS dépannage
# =========================================================================
"Serrurier Bruxelles - SVS dépannage": [
"Porte claquée vers 23h en rentrant les poubelles, j'étais en pyjama dans le froid. J'ai appelé SVS et le gars était là en moins de 40 minutes. Ouverture sans abîmer le cylindre, vraiment propre. Le tarif annoncé au tel a été respecté à la facture.",
"clé cassée dans la serrure de mon appart à Schaerbeek, j'ai paniqué un peu. Le technicien a extrait le bout coincé sans démonter toute la serrure, franchement bien joué. En 30 minutes c'était plié et la serrure tourne encore nickel.",
"Suite à une tentative d'effraction sur la porte d'entrée, fallait changer le cylindre en urgence. SVS est venu le lendemain matin et a posé un cylindre anti-perçage. Le devis a été respecté au centime près.",
"Bonne adresse pour une ouverture de porte rapide. Je suis sorti chercher du pain et la porte s'est refermée toute seule, classique. Le serrurier a ouvert en quelques minutes sans casser. Pas de surprise sur la facture, du coup je garde le numéro.",
"apres une tentative deffraction sur mon studio rue Royale, jai fait poser une serrure 3 points et un blindage léger. Le gars a bien expliqué chaque modèle et son prix avant. Travail propre et porte qui ferme mieux quavant en plus.",
"Ma fille de 17 ans s'était enfermée dehors un dimanche soir, panique totale. J'ai appelé SVS depuis le boulot, ils ont envoyé quelqu'un en 35 minutes. Ouverture sans dégâts et tarif weekend qui reste correct.",
"Cylindre qui tournait plus depuis 2 semaines, je forçais à chaque fois. Le technicien a vu tout de suite que c'était bloqué par l'usure interne. Remplacement en 1h chrono et la clé tourne maintenant comme du beurre.",
"Intervention de nuit après une tentative d'intrusion, on a appelé vers 1h du matin. Le gars a sécurisé la porte temporairement et est repassé le matin poser un nouveau cylindre certifié. Ça nous a enlevé un sacré poids pour pouvoir dormir.",
"Bon contact dès le téléphone, le mec a posé les bonnes questions avant de venir. Pose d'une serrure multipoints sur ma porte palière, ils ont protégé le sol et nettoyé après. Pas un euro de plus que le devis initial.",
"franchement bonne expérience, on emmenageait dans un appart bruxellois et on voulait changer toutes les serrures par sécurité. Trois cylindres remplacés en moins de 2 heures et clés copiées sur place. Je dors tranquille maintenant.",
"Clé perdue dans le métro, plus moyen de rentrer chez moi à Etterbeek. SVS a envoyé un serrurier en 45 min, ouverture propre sans toucher la porte. La facture correspondait pile à ce qui était annoncé.",
"Travail propre pour une pose de verrou supplémentaire sur ma porte d'entrée. Le technicien a perçé sans abîmer le bois et a aligné parfaitement. Voilà 4 mois maintenant et ça tient parfaitement.",
"Porte coincée à cause du gel un matin de janvier, impossible douvrir avec la cle. Le serrurier a degripé et regle la serrure en moins de 30 minutes. Depuis ca tourne sans accroc même quand il fait froid.",
"Mon vieux père de 78 ans avait son cylindre qui ne tournait plus côté Anderlecht. J'ai pris rdv depuis Liège, ils ont déplacé un technicien le lendemain. Tarif annoncé respecté et papa peut sortir tranquille.",
"Après un cambriolage chez ma sœur, sa porte ne fermait plus correctement. Pose d'une nouvelle serrure A2P et renfort sur le chambranle en une matinée. La porte claque comme une porte de coffre maintenant.",
],

# =========================================================================
# 2. Vitrier - Serrurier Saint-Gilles - SVS Dépannage
# =========================================================================
"Vitrier - Serrurier Saint-Gilles - SVS Dépannage": [
"Vitre du bas brisée par un ballon de foot des voisins, fallait sécuriser vite. SVS est passé le jour même mettre une planche puis remplacement du double vitrage 2 jours après. Le devis est resté identique à la facture.",
"Bon dépannage suite à une porte claquée chaussée de Waterloo. Le serrurier est arrivé en 50 minutes et a ouvert sans rayer le bois. Le tarif annoncé au téléphone correspondait à la facture finale.",
"j'avais une fenêtre PVC dont le double vitrage avait éclaté côté cour. Ils sont venus mesurer le lendemain et la vitre a été posée 6 jours après. Plus aucun courant d'air depuis et les voisins du dessus s'entendent moins.",
"Tentative d'effraction sur ma porte palière rue de la Victoire, le cylindre était à moitié arraché. Le technicien a posé un nouveau cylindre anti-bumping en 1h. Je peux enfin dormir sans angoisser.",
"Porte d'entrée bloquée un samedi matin avec ma fille qui devait aller à un anniversaire. SVS a réagi vite, ouverture en 25 minutes sans démonter. Tarif weekend resté raisonnable.",
"Intervention impec sur un velux abimé par la grêle de l'orage de mai. Bâche provisoire le jour même et remplacement complet 4 jours après. Aucune infiltration depuis les pluies de ce mois.",
"Mon studio à St Gilles avait un cylindre vraiment ancien qui menacait de bloquer. Remplacement par un modèle certifié, ils ont aussi recalé la gâche. Ca ferme bien plus net qu'avant.",
"Suite a un degat des eaux sur la fenetre cuisine, le cadre etait gondolé. Le vitrier a remplacé le vantail entier sans abimer le carrelage du rebord. Pose nickel et joints bien lisses.",
"clé restée à l'intérieur dimanche après-midi, classique en sortant promener le chien. Le serrurier était sur place en 35 minutes, ouverture sans aucune trace sur la porte. Facture conforme au devis téléphonique.",
"Vitre fissurée suite à une tentative d'intrusion sur notre porte d'entrée vitrée. Sécurisation immédiate avec une planche le soir et nouveau vitrage feuilleté posé 5 jours plus tard. On a passé l'hiver au sec malgré la pluie.",
"Ouverture porte appartement de mon frère qui s'était enfermé à cause d'un courant d'air. Le serrurier a bossé proprement avec sa lame, aucune marque visible. Devis téléphonique respecté à la facture.",
"Bonne intervention sur un changement complet de serrure 3 points dans un appart rue Théodore Verhaegen. Le technicien a expliqué les modèles et leurs niveaux de sécurité. Plus de jeu dans la porte maintenant.",
"Aprés un cambriolage chez mes parents agés, on a fait poser un blindage léger et changer le cylindre. Travail propre et discret, ils ont meme aspiré la sciure. Mes parents se sentent enfin en sécurité.",
"Vitre cuisine cassée par une chute de pot de fleurs du balcon du dessus. Vitrier sur place dans la matinée pour les mesures, vitrage posé 3 jours après. Joints bien faits et plus aucun sifflement de vent.",
"J'avais besoin d'un cylindre haute sécurité pour ma porte d'entrée vu que je suis souvent en déplacement. SVS m'a proposé un modèle débrayable très bien adapté. Ca fait 3 mois et la clé tourne parfaitement.",
],

# =========================================================================
# 3. Serrurier - Vitrier Ixelles - Delta dépannage
# =========================================================================
"Serrurier - Vitrier Ixelles - Delta dépannage": [
"Porte de mon appart bd Général Jacques claquée un soir avec mon chat resté dedans. Le serrurier Delta a debarqué en 30 minutes, ouverture rapide avec lame fine. Pas une trace sur le bois et tarif identique au devis.",
"Vitre du salon brisée par un cambriolage raté côté Flagey, on s'est réveillé sous le choc. Delta a sécurisé avec planche dans la matinée et posé un nouveau double vitrage feuilleté 4 jours après. On peut enfin laisser les rideaux ouverts.",
"clé cassée dans le cylindre vendredi soir, jallais devoir dormir chez un pote. Le mec de Delta a extrait le morceau sans démonter et le cylindre tourne encore. En 25 minutes c'était fait.",
"Suite à l'achat de notre appart à Ixelles, on a fait changer toutes les serrures par précaution. Pose de 2 cylindres certifiés en 1h30 et copies fournies sur place. Le devis a été respecté à l'euro.",
"Bon dépannage sur un Velux cassé par une grosse branche pendant l'orage de mars. Bâche provisoire immédiate et nouveau vitrage 6 jours après. Plus aucune trace d'humidité dans la chambre du haut.",
"j'ai appelé à 22h un mardi parce que ma porte palière refusait de se verrouiller. Le technicien Delta est arrivé en 40 minutes et a réajusté la gâche en plus de regraisser le mécanisme. La porte ferme nickel depuis.",
"Pose d'une serrure multipoints sur la porte d'entrée d'un nouveau locataire à Matongé. Le serrurier a percé le bois sans éclats et le résultat est impeccable. Aucun jeu et tarif respecté.",
"apres une tentative deffraction chez ma sœur, fallait changer le cylindre et renforcer la porte. Delta a posé un cylindre anti-perçage et une cornière anti-pince le lendemain matin. Elle se sent enfin chez elle.",
"Porte d'entrée bloquée un dimanche midi avec le repas familial en cours. Intervention en 35 min, ouverture sans toucher au cylindre d'origine. Facture conforme au devis téléphonique du matin.",
"Vitre baie coulissante fissurée par la chaleur l'été dernier. Mesure prise le lendemain et vitrage posé en moins d'une semaine. Pas un défaut sur les joints et l'isolation phonique est revenue.",
"Cylindre qui forçait depuis des mois sur mon ancien appart, ma mère s'inquiétait que je reste bloquée dehors. Remplacement complet par un modèle à carte de propriété en moins d'une heure. Plus aucun effort sur la clé.",
"Bonne expérience Delta sur une ouverture porte palière, jai fais tomber mes cles dans la trémie de la cage descalier. Le serrurier a ouvert en moins de 20 minutes proprement. Tarif honnête.",
"Vitre cassée par mon fils ado avec un ballon de basket dans le jardin. Vitrier passe le surlendemain prendre les mesures, pose 4 jours plus tard. La fenetre est comme neuve et le joint est lisse.",
"Suite à un déménagement, on avait juste les clés de l'ancien locataire et zéro confiance. Changement des 2 cylindres et pose d'un verrou supplémentaire en 2h. Je dors mieux maintenant.",
"Intervention sur un volet roulant dont la serrure était grippée, je n'arrivais plus à le bloquer la nuit. Le technicien a démonté, nettoyé et remplacé le mécanisme abimé. Ça fait 2 mois maintenant et tout fonctionne.",
],

# =========================================================================
# 4. Vitrier - Serrurier Ixelles - SVS dépannage (Emergency)
# =========================================================================
"Vitrier - Serrurier Ixelles - SVS dépannage": [
"urgence un samedi 2h du matin, ma porte palière sest refermee derriere moi avec le bébé encore dedans. SVS a debarqué en 25 minutes, ouverture en moins de 5. Tarif urgence resté correct.",
"Vitre brisée par un cambriolage manqué porte de Namur, on s'est levés sous adrénaline. Sécurisation par planche dans l'heure puis pose d'un nouveau double vitrage feuilleté 3 jours après. Plus moyen de défoncer aussi facilement.",
"Porte d'entrée claquee en rentrant les courses, mes voisins ont entendu mes jurons. Le serrurier était la en 35 minutes, ouverture avec lame fine sans laisser une trace. Pas de surprise sur la facture.",
"Suite à une tentative d'effraction côté Flagey, fallait sécuriser la porte de toute urgence. SVS est venu de nuit poser un cylindre temporaire et est repassé le lendemain installer le modèle définitif. On a pu dormir tranquilles.",
"clé bloquée dans le cylindre, impossible de tourner ni dextraire. Le technicien la débloquée et remplacé tout le bloc en une heure et demie. La clé tourne sans accroc depuis maintenant 5 mois.",
"Bonne intervention urgence sur un velux brise par la tempête davril. Bâche immédiate posée le soir même et vitrage neuf installé 4 jours plus tard. Plus aucune infiltration dans la chambre de ma fille.",
"Mon père de 80 ans s'est enfermé dehors un dimanche après être sorti chercher son journal. J'ai pris rdv depuis le boulot, SVS y était en 30 minutes. Tarif weekend resté raisonnable.",
"Cylindre forcé par une tentative d'intrusion alors qu'on était en vacances. Voisin a appelé SVS, ils ont sécurisé la porte et remplacé le bloc le jour même. La maison était impec à notre retour.",
"Intervention au top sur une serrure 3 points qui ne se verrouillait plus du tout. Le serrurier a démonté entièrement et changé deux pignons usés. La porte se ferme comme neuve.",
"Vitre fissurée du jour au lendemain à cause des écarts de temperature, double vitrage qui a lâché. Mesure prise rapidement et nouveau vitrage posé 5 jours après. Joints bien lisses et isolation impec.",
"franchement urgence bien gérée, ma clé sest cassée à 23h dans la serrure de notre porte palière. Le mec est arrivé en moins de 40 minutes, a tout démonté proprement et posé un cylindre neuf. Devis téléphonique respecté.",
"Pose d'un blindage discret sur la porte d'entrée suite à plusieurs cambriolages dans la cage d'escalier. SVS a tout fait en un après-midi sans saletés. Je me sens vraiment plus en sécurité maintenant.",
"apres avoir perdu mon trousseau de cles dans le tram, jai du faire changer tous les cylindres en urgence. SVS sest organisé pour le lendemain matin, 3 cylindres changés en 2 heures. La facture matchait pile le devis du tel.",
"Vitre fenêtre chambre cassée par une chute d'arbre pendant la tempête. SVS a sécurisé le soir avec un panneau bois et remplacé le double vitrage 4 jours après. La chambre est nickel et le bruit extérieur a baissé.",
"Bonne adresse en urgence, porte de service du commerce qui ne fermait plus à la clé un dimanche soir. Le technicien a réparé la gâche tordue en 45 minutes. Pas besoin de tout changer et tarif vraiment correct.",
],

# =========================================================================
# 5. Vitrier - Serrurier Uccle - SVS dépannage
# =========================================================================
"Vitrier - Serrurier Uccle - SVS dépannage": [
"Porte claquée en rentrant du marché du Bourdon, mon mari avait pris l'autre trousseau au boulot. SVS sur place en 30 minutes, ouverture sans la moindre rayure. Tarif weekend tout à fait correct.",
"Vitre fenêtre cuisine fissurée par un caillou de la tondeuse du voisin. Le vitrier a mesuré le mardi et posé le vitrage feuilleté le vendredi suivant. Pas un défaut sur le joint silicone et la facture matchait le devis.",
"clé brisée dans la serrure de notre porte palière dans un immeuble av Brugmann. Le serrurier a extrait le morceau et changé le cylindre en moins d'une heure. La porte ferme mieux qu'avant.",
"Tentative d'effraction sur la porte d'entrée de notre maison rue Vanderkindere, plusieurs traces de pince. SVS est venu poser un cylindre haute sécurité et un cornière anti-pince le lendemain. Plus de stress quand on part le week-end.",
"j'ai appelé un dimanche matin parce que mon père s'était enfermé à l'extérieur en allant fumer. Intervention en 35 minutes, ouverture propre sans dégât. Tarif annoncé tenu à l'euro près.",
"Pose d'un nouveau cylindre certifié sur notre porte d'entrée après emménagement à Calevoet. Le technicien a expliqué la différence entre les modèles avant de commencer. Travail soigné et 0 désordre laissé derrière.",
"Bonne intervention sur une baie vitrée fissurée par le froid de février. Mesures prises rapidement et vitrage thermique posé en 5 jours. La pièce est moins froide depuis et le bruit de la rue a baissé.",
"Porte d'appart bloquée fermée par le vent, mon chien à l'intérieur sans gamelle d'eau. Le serrurier SVS est arrivé en 28 minutes et a ouvert avec une lame, sans toucher au cylindre. Pas un euro de plus que le devis téléphonique.",
"Serrure 3 points qui forcait depuis longtemps, jentendais le mecanisme grincer. Le technicien a tout demonté et remplacé deux ressorts usés. La cle tourne sans aucun effort maintenant.",
"Vitrage abîmé par un coup de raquette de mon fils, le ballon a fini dans la fenêtre cuisine. Le vitrier a remplacé le simple vitrage par un double, joints propres et appui bien net. Plus aucun courant d'air.",
"Suite à un cambriolage chez la voisine, on a fait poser un blindage léger sur notre porte palière. Travail discret sur la matinée, ils ont meme passé l'aspirateur après. Ma femme se sent plus tranquille la nuit.",
"clé restée bloquée dans le verrou inférieur, plus moyen de la tourner. Intervention en 40 minutes avec extraction propre et remplacement du verrou usé. Facture conforme au devis et clés copiées sur place.",
"Pose dune serrure multipoints sur une porte palière qui navait quun cylindre de base, jetais pas tranquille. Le serrurier a expliqué chaque etape et tout posé en 2 heures. Trois mois plus tard la porte est toujours impec.",
"Vitre porte arrière brisée par une branche tombée lors des grands vents. SVS a posé un panneau provisoire la veille au soir et remplacé le vitrage 3 jours plus tard. Pas un éclat de verre oublié dans le jardin.",
"Bon contact dès l'appel, j'avais besoin d'un avis sur le renforcement de notre porte de garage. Le technicien est venu gratuitement pour un état des lieux. Pose de la serrure renforcée en moins de 2 heures et tarif honnête.",
],

# =========================================================================
# 6. Serrurier Uccle - Delta Services
# =========================================================================
"Serrurier Uccle - Delta Services": [
"Porte claquée en sortant arroser les plantes dans le jardin, j'avais oublié les clés sur la table. Delta a envoyé un serrurier en 30 minutes, ouverture sans dégâts en quelques minutes. Le tarif annoncé au tel correspondait à la facture.",
"Cylindre forcé suite à une tentative d'effraction sur notre porte palière, je m'en suis rendu compte au retour de vacances. Delta Services a remplacé le cylindre par un modèle anti-perçage le jour même. Plus aucune trace de jeu dans la porte.",
"clé cassée dans la serrure de la cave un soir, le morceau bloqué empêchait de fermer. Le serrurier a extrait avec un crochet sans démonter et la serrure tourne encore comme avant. En 25 minutes c'était plié.",
"Suite à l'achat de notre maison à Uccle, on voulait par sécurité changer toutes les serrures. Delta a remplacé 3 cylindres et 2 verrous en une matinée. Le devis n'a pas bougé d'un euro à la facture.",
"Bonne intervention un samedi soir, ma fille avait oublié sa clé en allant chez sa copine. Le serrurier de chez Delta était sur place en 40 minutes, ouverture propre sans la moindre marque. Pas de mauvaise surprise sur le ticket.",
"Pose d'une serrure 3 points sur notre porte d'entrée jugée trop faible par l'assurance. Le gars a expliqué chaque option avant de poser, travail propre et discret. Plus aucun jeu et la porte claque comme un coffre.",
"j'avais besoin d'un cylindre haute sécurité après un cambriolage chez ma voisine du dessous. Delta a proposé un modèle à carte de propriété et a posé en moins d'une heure. Je dors tranquille depuis.",
"Intervention sur une serrure de boite aux lettres collective de notre résidence av Defré. Le serrurier a remplacé tout le bloc et fourni 4 clés. Boite refermée nickel et plus aucune lettre volée.",
"Cylindre grippé par l'humidité dans la cave depuis l'hiver, jarrivais plus a fermer. Le technicien Delta a démonté, nettoyé et regraissé le mécanisme. La clé tourne sans effort maintenant.",
"Porte palière de mon studio bloquée fermée un dimanche midi, j'étais devant en chaussons. Delta a réagi vite, ouverture en 35 minutes sans toucher au bois. Facture conforme au devis téléphonique.",
"Suite à une rupture, on a fait changer toutes les serrures de l'appart pour notre tranquillité. Travail propre et rapide, ils ont posé 2 cylindres certifiés en une heure et demie. Tarif annoncé respecté.",
"Bon dépannage sur un verrou supplémentaire posé sur notre porte d'entrée principale. Le serrurier a percé sans abîmer le chambranle et a aligné parfaitement. Ca fait 4 mois et tout fonctionne nickel.",
"Pose dun blindage discret sur la porte dentree de notre studio aprés une serie deffractions dans le quartier. Delta a tout fait en un apres-midi sans aucune sallissure. On respire enfin un peu.",
"clé restée à lintérieur après que ma fille a refermé la porte derrière moi. Le serrurier a ouvert avec une lame fine en moins de 15 minutes. Tarif weekend complétement raisonnable.",
"Intervention sur un coffre-fort dont jai perdu le code suite à un déménagement. Le technicien Delta a ouvert sans abîmer le coffre et réinitialisé le code. Ca fait 2 mois maintenant et tout fonctionne parfaitement.",
],

# =========================================================================
# 7. Vitrier - Serrurier Forest - SVS dépannage
# =========================================================================
"Vitrier - Serrurier Forest - SVS dépannage": [
"Vitre porte d'entrée fracassée par une tentative d'intrusion la nuit, on a sursauté à 3h du matin. SVS a sécurisé immédiatement et posé un vitrage feuilleté antivol 4 jours plus tard. Plus aucun bruit ne passe non plus.",
"Porte claquée en partant chercher du pain rue Saint-Denis, on est restés une heure devant. Le serrurier était la en 35 minutes, ouverture en quelques minutes avec une lame. Pas de surprise sur la facture.",
"clé cassée dans le cylindre d'une fenetre oscillo-battante de notre cuisine. Le technicien a extrait le bout en moins de 20 minutes et la fenêtre se ferme parfaitement depuis. Tarif vraiment honnete.",
"Tentative d'effraction sur la porte palière côté place Saint-Antoine, cylindre arraché à moitié. SVS a remplacé par un modèle anti-perçage le lendemain matin et renforcé la gâche. La porte est nettement plus solide.",
"Bon dépannage suite à une vitre cassée par un caillou de tondeuse, fenêtre arrière du salon. Mesure prise dans la journée et vitrage posé 5 jours après. Joint silicone bien tiré et appui propre.",
"Pose dune serrure 3 points sur notre porte palière au 4e étage rue de Mérode. Le serrurier a expliqué la difference avec une serrure mono-point et tout posé en moins de 2 heures. Plus aucun jeu dans la porte.",
"j'ai eu une grosse galère avec mon cylindre qui forçait depuis 3 semaines. Le technicien SVS la remplacé par un modele certifié et la clé tourne maintenant sans aucun effort. Ca fait 4 mois maintenant et rien à signaler.",
"Vitre baie vitrée du jardin fissurée par les écarts de température entre l'été et l'automne. Vitrier sur place pour les mesures le lendemain et pose 6 jours plus tard. La piece est de nouveau bien isolée.",
"Porte d'entrée bloquée fermée un dimanche soir, mon mari a essayé de forcer et la clé a tourné dans le vide. SVS a debarqué en 40 minutes, démonté et remplacé le cylindre cassé. Tarif weekend tout à fait correct.",
"Intervention au top sur un velux brisé par la grêle d'avril. Bâche immédiate et nouveau vitrage 4 jours après. Plus aucune infiltration dans le grenier transformé en chambre.",
"Suite a un cambriolage chez les voisins de palier, on a fait poser un cylindre anti-bumping et un verrou de sécurité supplémentaire. Travail propre et discret, on est complètement rassurés. Devis respecté à l'euro.",
"clé perdue à la salle de sport, jai du faire ouvrir et changer le cylindre en urgence. SVS a fait les deux dans la meme intervention en moins de 2 heures. Et la clé copiée sur place.",
"Vitre du sas d'entrée du commerce cassée par un coup de pied dans la nuit. SVS a sécurisé par planche le matin et posé un nouveau vitrage feuilleté 3 jours plus tard. Plus aucune impression d'insécurité.",
"Pose d'un blindage discret sur notre porte palière vieillissante. Le technicien a tout posé en un après-midi sans bruit ni sciure partout. Ma copine se sent enfin chez elle.",
"apres avoir cassé ma cle dans la serrure du garage, plus moyen de sortir la voiture. Le serrurier SVS a extrait le bout, remplacé le cylindre et tout testé en moins d'une heure. Facture exactement au devis annoncé.",
],

# =========================================================================
# 8. Vitrier - Serrurier Zaventem - SVS dépannage
# =========================================================================
"Vitrier - Serrurier Zaventem - SVS dépannage": [
"Porte d'entrée claquée en partant à l'aéroport, j'allais rater mon vol. SVS a envoyé un serrurier en moins de 25 minutes, ouverture rapide et sans dégât. Tarif urgence très correct vu l'heure du matin.",
"Vitre baie cassée par les vibrations d'un avion qui passait bas selon le vitrier. Mesure prise rapidement et nouveau vitrage thermique posé 5 jours après. Plus aucun bruit excessif depuis.",
"clé cassée dans le cylindre alors quil faisait moins 5 dehors, mes doigts gelés. Le technicien a extrait le morceau et remplacé tout le bloc en moins d'une heure. Tarif annoncé respecté.",
"Tentative d'effraction sur la porte d'un appartement loué à des locataires de passage. SVS a installé un cylindre haute sécurité le lendemain matin. Les nouveaux locataires sont rassurés.",
"j'ai appelé pour un dépannage sur ma serrure 3 points qui ne verrouillait plus le point haut. Le serrurier est venu dans la demie-journée, démonté et changé deux pignons usés. La porte ferme à clé sans plus aucun forçage.",
"Bon dépannage suite à un cylindre forcé par tentative douverture au tournevis. SVS a tout remplacé par un modèle anti-perçage en moins d'une heure et demie. Pas un euro de plus que le devis téléphonique.",
"Porte palière bloquée fermée à cause du gel sur les rails du verrou. Le technicien a degrippé, nettoyé et regraissé tout le mécanisme. Depuis ça tourne sans accroc même quand il gèle.",
"Vitre fenêtre cuisine impactée par un caillou du jardin du voisin, en moins de 24h SVS a sécurisé. Pose du nouveau double vitrage 4 jours plus tard avec joints bien faits. La piece a retrouvé son calme.",
"Suite a un dégat des eaux sur la fenetre PVC, le vantail etait gondolé. Vitrier sur place pour les mesures et remplacement du vantail entier en moins dune semaine. Pose nickel et plus aucun courant dair.",
"apres avoir perdu mes cles dans le parking de laeroport, jai du changer le cylindre par precaution. SVS a posé un cylindre certifié et copié 4 cles sur place. La porte ferme nickel et je dors tranquille.",
"Intervention sur une serrure de garage qui forcait depuis l'hiver, ma femme arrivait plus à sortir la voiture. Le serrurier a démonté, nettoyé et remplacé le mécanisme abimé. Plus aucun forçage maintenant.",
"Pose dun verrou supplémentaire discret sur la porte de service de notre maison. Travail propre et bien fait en moins de deux heures. Tarif annoncé tenu à la facture finale.",
"clé bloquée dans le cylindre en revenant du boulot un vendredi soir, plus moyen davancer. Le technicien SVS la débloquée en moins de 30 minutes sans démonter. Facture conforme au devis téléphonique.",
"Vitre porte vitrée du sas d'entrée fissurée par un choc, fallait sécuriser avant les vacances. Pose d'un vitrage feuilleté 4 jours après les mesures avec joints lisses. Plus aucune impression de fragilité.",
"Bonne intervention en pleine nuit sur ma porte palière qui refusait obstinément de se verrouiller. Le serrurier a réajusté la gâche et regraissé le mécanisme en moins de 40 minutes. La porte ferme comme neuve maintenant.",
],

# =========================================================================
# 9. Vitrier - Serrurier Auderghem - SVS depannage
# =========================================================================
"Vitrier - Serrurier Auderghem - SVS depannage": [
"Porte palière claquée en allant chercher mes enfants à l'école juste à coté. SVS a envoyé quelqu'un en 30 minutes, ouverture sans même toucher au cylindre. Tarif vraiment correct vu l'heure tardive.",
"Vitre baie côté jardin fracturée par une chute d'arbre pendant la tempête de mars. Le vitrier a sécurisé le soir même avec une planche puis posé un nouveau vitrage thermique 5 jours plus tard. Plus aucun courant d'air.",
"clé cassée dans la serrure de la porte d'entrée un dimanche matin, juste avant un anniversaire de famille. Le serrurier a extrait et remplacé le cylindre en moins de 50 minutes. Le tarif weekend est resté raisonnable.",
"Suite à une tentative d'effraction côté avenue Schaller, fallait sécuriser au plus vite. SVS a posé un cylindre anti-perçage et renforcé la gâche le lendemain matin. La porte est nettement plus solide.",
"Bon dépannage sur un velux fendu par la grêle du printemps. Bâche posée le jour de l'appel et remplacement complet 4 jours après. Plus aucune trace d'humidité au plafond.",
"j'ai fait poser une serrure 3 points sur la porte palière de mon appart parce que l'ancienne ne m'inspirait pas confiance. Travail propre en 2 heures, ils ont nettoyé après. La porte claque maintenant comme un coffre.",
"Cylindre qui forcait depuis plusieurs mois, j'avais peur de rester bloqué dehors. Le technicien la remplacé par un modèle anti-bumping en moins d'une heure. Plus aucun effort sur la clé maintenant.",
"Vitre cuisine cassée par un caillou projeté lors d'un coup de vent. Vitrier sur place dans la journée pour les mesures, pose 3 jours après. Le joint silicone est parfait.",
"Porte d'appart bloquée fermée par une mauvaise manipulation de la serrure d'origine. SVS a ouvert en 35 minutes sans dégât, puis a réajusté la gâche dans la foulée. Plus aucun forçage.",
"Intervention chez ma mère âgée qui avait sa porte coincée, panique au téléphone. Le serrurier a ouvert en moins de 30 minutes et a graissé le mecanisme. Tarif vraiment correct, je garde le contact.",
"apres un cambriolage chez les voisins de palier, on a fait poser un blindage discret et changer le cylindre. SVS a tout fait en un apres-midi sans bruit. Je peux enfin laisser ma femme seule le soir.",
"Pose dun verrou supplementaire sur ma porte palière, un modele a code que javais commandé. Le technicien a aligné et fixé en moins dune heure. Aucun jeu et la porte ferme nickel.",
"Vitre porte arrière de la maison brisée par un coup de balle de tennis du chien. Mesure prise rapidement et vitrage posé 4 jours après. Plus rien à signaler depuis et le jardin reste sécurisé.",
"Suite à la perte de mon trousseau de clés au boulot, j'ai fait changer le cylindre pour ne pas prendre de risque. SVS a remplacé par un modele certifié en moins d'une heure et fourni 4 clés. Je dors plus tranquille.",
"clé bloquée en plein milieu de la course de fin daprés-midi, plus moyen ni davancer ni de sortir. Le serrurier a debloqué et fait tourner avec un produit specifique. Le cylindre fonctionne nickel depuis 3 mois.",
],

# =========================================================================
# 10. Vitrier - Serrurier Waterloo - SVS depannage
# =========================================================================
"Vitrier - Serrurier Waterloo - SVS depannage": [
"Porte d'entrée claquée en sortant le chien après le souper, j'avais oublié mes clés. SVS a envoyé un serrurier en 40 minutes, ouverture rapide sans la moindre rayure. Tarif annoncé tenu jusqu'à la facture.",
"Vitre porte vitrée arrière fracassée par la chute d'une grande branche pendant l'orage de mai. Le vitrier a sécurisé immédiatement par planche puis posé un vitrage feuilleté 5 jours plus tard. Plus aucune crainte d'intrusion par là.",
"clé cassée dans le cylindre de la porte palière, je rentrais des courses avec les bras chargés. Le serrurier a extrait le morceau et changé le cylindre en moins d'une heure. La clé tourne nickel depuis.",
"Suite à une tentative d'intrusion par la baie côté terrasse, fallait renforcer la sécurité de la maison. SVS a posé un cylindre haute sécurité et un verrou supplémentaire en une matinée. On dort beaucoup plus tranquilles.",
"Bon dépannage sur un velux du grenier brisé par la grêle, infiltrations le soir même. Bâche immédiate et nouveau vitrage 4 jours après. Plus aucune trace d'humidité dans le grenier transformé en bureau.",
"j'ai fait changer toutes les serrures après l'achat de notre maison sur la chaussée de Bruxelles. Trois cylindres certifiés posés en moins de 2 heures. Le devis a été respecté à l'euro près.",
"Cylindre qui forçait depuis longtemps, ma fille n'arrivait plus à fermer en partant à l'école. Le technicien a remplacé par un modèle anti-perçage en 1h chrono. Plus aucun effort sur la clé maintenant.",
"Intervention sur une serrure 3 points qui ne verrouillait plus du tout en partie haute. Le serrurier a tout démonté, nettoyé et remplacé deux pignons usés. La porte ferme comme un coffre maintenant.",
"Vitre fenêtre cuisine cassée par un caillou de tondeuse du voisin, classique. Mesure prise dans la journée et vitrage posé 3 jours après. Joints bien faits et appui nickel.",
"Porte d'appartement bloquée fermée par un courant d'air, ma femme attendait avec les courses. SVS a réagi vite, ouverture en 30 minutes sans toucher au bois. Pas de mauvaise surprise sur la note.",
"Pose d'un blindage discret sur la porte d'entrée suite à des cambriolages dans le quartier. Travail propre et discret sur un après-midi, ma femme se sent enfin chez elle. Plus aucune crainte.",
"clé restée dans la serrure côté intérieur, ma fille avait fermé sans prévenir. Le serrurier a ouvert en moins de 25 minutes avec une lame fine. Tarif weekend vraiment honnête.",
"Bon contact dès l'appel téléphonique, j'avais besoin d'un conseil sur le renforcement de ma porte palière. Le technicien est venu gratuitement faire un état des lieux. Pose du nouveau cylindre en 1h.",
"Vitre baie vitrée fissurée du jour au lendemain à cause des écarts thermiques. SVS a mesuré rapidement et posé un nouveau vitrage thermique 6 jours après. Le salon est plus calme et mieux isolé.",
"apres avoir perdu mon trousseau de cles dans le bus, jai fais changer le cylindre par precaution. SVS a remplacé par un modèle à carte de propriété en moins d'une heure. Je dors tranquille depuis.",
],

# =========================================================================
# 11. Serrurier Waterloo - SVS Depannage
# =========================================================================
"Serrurier Waterloo - SVS Depannage": [
"Cylindre bloqué en pleine soirée alors que je rentrais du boulot, panique totale. SVS a envoyé un serrurier en 35 minutes, débloqué et regraissé le mécanisme. Pas un euro de plus que le devis téléphonique.",
"Porte palière de notre appart drève Richelle fermée à clé par ma fille sans prévenir. Le serrurier a ouvert en moins de 20 minutes avec une lame, sans toucher au cylindre. Tarif annoncé respecté.",
"Suite à un cambriolage chez les voisins, j'ai voulu changer le cylindre par précaution. SVS a posé un modèle anti-bumping le lendemain et fourni 4 clés. Je me sens vraiment plus en sécurité.",
"clé cassée dans la serrure principale un dimanche soir, juste avant de partir en weekend. Le technicien a extrait le morceau et remplacé tout le bloc en moins d'une heure. La clé tourne sans accroc depuis.",
"Bon dépannage suite à une porte d'entrée claquée avec le repas en train de brûler dans le four. Intervention en 25 minutes, ouverture rapide sans dégâts. Pas de surprise sur la facture.",
"Pose dune serrure 3 points sur la porte palière de mon studio loué, plus rassurant pour les locataires. Travail soigné en moins de 2 heures, ils ont aspiré derrière. La porte ferme comme un coffre.",
"apres une tentative deffraction par fenetre cassée la nuit, jai fait poser un cylindre haute sécurité dans la foulée. SVS a tout fait le matin même. La porte est nettement plus solide maintenant.",
"j'avais une serrure qui grinçait depuis des mois, je sentais qu'elle allait lâcher. Le serrurier a démonté, nettoyé et changé deux pignons usés. Plus aucun bruit et la clé tourne en douceur.",
"Intervention au top sur une porte de cave bloquée fermée à cause de l'humidité. Le technicien a démonté, séché et regraissé le mécanisme. Depuis ça tourne sans accroc même par temps humide.",
"Cylindre forcé par une tentative douverture au tournevis pendant le weekend. SVS la remplacé par un modèle certifié en moins d'une heure. Pas de mauvaise surprise sur la note.",
"Bonne intervention urgence en pleine nuit sur ma porte palière qui refusait de se verrouiller. Le serrurier a reajusté la gache et regraissé le mecanisme en 40 minutes. Tarif honnete.",
"clé perdue à la piscine, jai du faire changer le cylindre en urgence. SVS a remplacé par un modele anti-perçage et copié 3 cles. Je dors tranquille depuis maintenant 4 mois.",
"Pose d'un verrou supplémentaire sur ma porte palière, modèle à code que javais commandé en ligne. Le technicien a aligné et fixé en 1h. Aucun jeu et l'installation est nickel.",
"Suite a un déménagement, on a fait changer toutes les serrures de notre nouvelle maison. Deux cylindres et un verrou posés en une matinée. Le devis est resté identique à la facture.",
"Intervention sur une serrure de garage qui forcait depuis l'hiver. Le serrurier a démonté, nettoyé et remplacé le mécanisme abimé. Plus aucun forçage et porte de garage qui ferme nickel depuis 5 mois.",
],

# =========================================================================
# 12. Serrurier Waterloo - Delta Services
# =========================================================================
"Serrurier Waterloo - Delta Services": [
"Porte d'entrée claquée en sortant les poubelles, j'étais en chaussons dans la cour. Delta a envoyé un serrurier en 30 minutes, ouverture en quelques minutes avec une lame fine. Tarif annoncé respecté.",
"Cylindre forcé suite à une tentative d'effraction la nuit, marques de pince visibles. Delta Services a remplacé par un cylindre anti-perçage le lendemain matin. La porte est beaucoup plus solide.",
"clé cassée dans la serrure de la porte garage, plus moyen de sortir la voiture pour aller bosser. Le serrurier a extrait et remplacé le cylindre en moins de 45 minutes. La facture matchait pile le devis téléphonique.",
"Bon dépannage un dimanche matin sur ma porte palière bloquée. Le technicien Delta a réagi vite, ouverture sans la moindre rayure. Pas un euro de plus que le devis.",
"Suite a l'achat de notre maison sur l'avenue de la Petite Espinette, on a voulu changer toutes les serrures. Delta a posé 3 cylindres certifiés en une matinée. Travail soigné et chantier propre.",
"j'ai fait poser une serrure 3 points sur ma porte palière vieillissante, l'ancienne ne m'inspirait pas confiance. Le serrurier a tout fait en moins de 2 heures. La porte ferme nickel depuis 5 mois.",
"Intervention sur un cylindre qui grippait depuis l'hiver, je devais forcer à chaque fois. Le technicien la démonté, nettoyé et regraissé. Plus aucun effort sur la clé depuis.",
"Pose d'un blindage discret sur ma porte palière après des cambriolages dans le voisinage. Delta a tout fait en un après-midi sans bruit ni saletés. Je me sens chez moi en sécurité.",
"clé perdue à la salle de gym, jai préféré faire changer le cylindre par sécurité. Delta a remplacé par un modèle certifié et copié 4 cles sur place. Pas de mauvaise surprise sur la facture.",
"Cylindre forcé par une tentative douverture au tournevis pendant les vacances. Delta a remplacé tout le bloc par un modèle anti-bumping en moins d'une heure. Tarif honnête.",
"Porte palière bloquée fermée par un courant d'air, ma fille à l'intérieur avec mon chien. Le serrurier était sur place en 35 minutes, ouverture sans toucher au bois. Tarif raisonnable.",
"Bonne intervention sur une serrure 3 points qui ne verrouillait plus en partie haute. Le technicien a démonté entièrement, changé deux pignons et regraissé. La porte se ferme comme neuve.",
"Pose d'un verrou supplémentaire sur la porte de service de notre maison. Delta a percé sans abîmer le chambranle et fixé proprement. Plus aucune crainte d'intrusion par là.",
"Suite à une rupture, jai fait changer toutes les serrures de l'appart pour ma tranquillité. Delta a posé 2 cylindres certifiés et un verrou en 1h30. Je dors tranquille maintenant.",
"clé bloquée dans le cylindre un vendredi soir, plus moyen de tourner. Le serrurier la débloqué et remplacé le bloc usé en moins d'une heure. Facture conforme au devis téléphonique du matin.",
],

# =========================================================================
# 13. Serrurier Namur - SVS depannage (Emergency)
# =========================================================================
"Serrurier Namur - SVS depannage": [
"Porte d'entrée claquée en pleine nuit, je rentrais d'une soirée et javais oublié mes clés. SVS a envoyé un serrurier en 35 minutes, ouverture sans la moindre rayure. Tarif urgence completement raisonnable.",
"Cylindre forcé suite à une tentative d'effraction sur ma porte palière rue de Bruxelles. SVS a remplacé par un modèle anti-perçage le lendemain. La porte est nettement plus solide.",
"clé cassée dans la serrure de mon appart sur l'avenue Cardinal Mercier, je rentrais du boulot fatigué. Le technicien a extrait le morceau et remplacé le bloc en moins d'une heure. Facture conforme au devis du tel.",
"Bon dépannage urgence un dimanche matin, ma porte refusait obstinément de se verrouiller. Le serrurier a réajusté la gache et regraissé le mécanisme en 40 minutes. Tarif weekend honnête.",
"Suite à un cambriolage chez ma sœur en plein centre, jai fais poser un cylindre haute securité en urgence. SVS la posé le lendemain matin avec un blindage léger. Elle peut enfin dormir tranquille.",
"j'avais besoin d'une ouverture porte en urgence un samedi soir, jétais sorti chercher du pain. Le serrurier était la en moins de 30 minutes avec une lame fine. Pas de mauvaise surprise sur la facture.",
"Pose d'une serrure 3 points sur la porte palière de mon studio à Salzinnes, jamais rassuré avec l'ancienne. Travail propre en 2 heures, ils ont aspiré derrière. La porte ferme comme un coffre.",
"clé bloquée dans le cylindre un soir d'hiver, le gel avait grippé le mecanisme. Le technicien a degripé, nettoyé et regraissé. Depuis ça tourne sans accroc même quand il gele.",
"Intervention au top sur une porte de garage dont la serrure ne fonctionnait plus, plus moyen de sortir la voiture. Le serrurier a démonté et changé tout le bloc en moins d'une heure. Pas un euro de plus que prévu.",
"Cylindre forcé par une tentative douverture au tournevis pendant que jétais en vacances. SVS la remplacé par un modèle certifié dès mon retour. La maison est complètement sécurisée maintenant.",
"Bonne intervention en urgence sur une serrure de porte vitrée qui se bloquait. Le technicien la débloquée et remplacée par un modèle adapté au vitrage. La porte ferme nickel.",
"clé perdue lors dune randonnée en Ardennes, jai du faire changer le cylindre en rentrant. SVS a posé un modele à carte de propriété en moins d'une heure et copié 4 clés. Je dors tranquille depuis.",
"Pose d'un verrou supplémentaire sur la porte de mon appart, modele à code que j'avais commandé. Le serrurier a aligné et fixé en moins de 50 minutes. Aucun jeu et l'installation est nickel.",
"Suite a un déménagement vers le centre de Namur, jai fait changer les 2 cylindres de notre nouvel appart. SVS a remplacé en une matinée par des modèles certifiés. Tarif annoncé tenu jusqu'à la facture.",
"Intervention sur une serrure de boite aux lettres collective de la résidence. Le technicien a remplacé tout le bloc et fourni les copies. Plus aucune lettre volée depuis et le bloc est nickel.",
],

# =========================================================================
# 14. Vitrier - Serrurier La Louvière - SVS depannage
# =========================================================================
"Vitrier - Serrurier La Louvière - SVS depannage": [
"Vitre fenêtre cuisine fracassée par un caillou de tondeuse du jardin voisin. Le vitrier a mesuré le lendemain et posé un nouveau double vitrage 4 jours plus tard. Plus aucun courant d'air et joints bien lisses.",
"Porte d'entrée claquée en sortant promener le chien rue Sylvain Guyaux, javais zappé les clés. SVS a envoyé un serrurier en 35 minutes, ouverture rapide sans rayure. Tarif annoncé tenu jusqu'à la facture.",
"clé cassée dans la serrure de la porte palière du 3e étage, je rentrais du boulot. Le technicien a extrait le morceau et changé tout le cylindre en moins d'une heure. La clé tourne nickel depuis.",
"Tentative d'effraction sur la porte palière, cylindre arraché à moitié pendant la nuit. SVS a remplacé par un cylindre anti-perçage et renforcé la gâche le lendemain matin. La porte est plus solide qu'avant.",
"Bon dépannage sur un velux brise par la grele de mars, infiltrations dans le grenier. Bâche immédiate posée le soir et vitrage neuf 4 jours après. Plus aucune trace dhumidité au plafond.",
"Pose dune serrure 3 points sur ma porte palière vieillissante après une série deffractions dans l'immeuble. Le serrurier a tout fait en moins de 2 heures avec un chantier propre. La porte ferme nickel.",
"j'avais un cylindre qui forçait depuis plusieurs mois, javais peur de rester bloqué. Le technicien la remplacé par un modèle anti-bumping en moins d'une heure. Plus aucun effort sur la cle.",
"Vitre baie cassée par une chute de branche pendant la tempête, fallait sécuriser vite. Vitrier sur place dans la matinée puis pose du nouveau vitrage 5 jours après. Joints bien lisses et appui propre.",
"Porte d'appart bloquée fermée par un courant d'air, ma copine attendait dans le couloir. SVS a réagi vite, ouverture en 30 minutes sans toucher au bois. Pas de surprise sur la facture.",
"clé restée dans le verrou intérieur, mon fils ado avait fermé sans réfléchir. Le serrurier a ouvert en moins de 25 minutes avec une lame fine. Tarif vraiment honnête.",
"Pose dun blindage discret sur la porte d'entrée après deux tentatives d'effraction dans le bâtiment. Travail propre et discret en un après-midi. Plus aucune crainte d'intrusion.",
"Intervention sur une serrure de garage qui forçait depuis l'hiver, plus moyen de sortir la voiture. Le technicien a démonté et remplacé le mécanisme abimé en 1h. Tarif honnête.",
"Vitre fenêtre chambre fissurée du jour au lendemain par les écarts thermiques. SVS a mesuré rapidement et posé un nouveau vitrage 5 jours après. Plus aucun sifflement de vent.",
"Suite a la perte de mes cles à la patinoire, jai fait changer le cylindre par precaution. SVS a remplacé par un modèle certifié en moins d'une heure. Je dors tranquille depuis 4 mois.",
"Bonne intervention urgence en pleine nuit pour ma porte palière qui ne se verrouillait plus. Le serrurier a réajusté la gache et regraissé le mécanisme en 40 minutes. Tarif weekend vraiment correct.",
],

# =========================================================================
# 15. Vitrier - Serrurier Ath - SVS depannage
# =========================================================================
"Vitrier - Serrurier Ath - SVS depannage": [
"Porte d'entrée claquée en allant chercher le pain rue de Pintamont, ma femme dormait encore. SVS a envoyé un serrurier en 40 minutes, ouverture sans la moindre rayure. Tarif annoncé respecté.",
"Vitre cuisine cassée par un coup de balle de tennis du chien, classique avec un labrador. Le vitrier a mesuré dans la journée et posé un nouveau double vitrage 4 jours après. Joints bien lisses.",
"clé cassée dans le cylindre de notre porte palière, le bout coincé empêchait de fermer. Le technicien a extrait sans démonter et la serrure tourne encore nickel. En moins de 30 minutes c'était plié.",
"Tentative d'effraction sur la porte d'entrée de notre maison rue d'Houtaing. SVS a posé un cylindre anti-perçage et renforcé la gâche le lendemain matin. Plus aucune crainte d'intrusion.",
"j'ai fait changer toutes les serrures après emménagement dans notre nouvelle maison. SVS a remplacé 3 cylindres en une matinée par des modèles certifiés. Le devis a été respecté à l'euro.",
"Bon dépannage suite à un cylindre qui forçait depuis longtemps, je sentais qu'il allait lâcher. Le serrurier la remplacé par un modèle anti-bumping en moins d'une heure. Plus aucun effort sur la clé.",
"Pose d'une serrure 3 points sur la porte palière du bureau qu'on loue. Travail propre en 2 heures avec un chantier nickel. La porte ferme comme un coffre maintenant.",
"Intervention au top sur un velux brisé par la grêle. Bâche immédiate posée le soir et vitrage neuf 4 jours après. Plus aucune trace d'humidité au plafond du grenier.",
"Vitre baie côté jardin fissurée par les écarts thermiques de l'automne. Vitrier sur place pour les mesures et pose 5 jours après. La piece est plus calme et mieux isolée.",
"clé perdue à la foire d'Ath, jai du faire changer le cylindre par precaution. SVS a remplacé par un modèle certifié en moins d'une heure et copié 4 clés. Je dors tranquille.",
"Porte d'appart bloquée fermée par un courant d'air, ma fille à lintérieur avec le chat. SVS a réagi vite, ouverture en 35 minutes sans dégât. Pas de mauvaise surprise sur la note.",
"Pose d'un verrou supplémentaire sur la porte de service de notre maison à la campagne. Le technicien a aligné et fixé proprement en 1h. Aucun jeu et installation nickel.",
"Cylindre forcé par une tentative douverture au tournevis pendant le weekend. SVS la remplacé par un modèle certifié en moins d'une heure et demie. La porte ferme bien plus solidement maintenant.",
"Vitre porte arrière brisée par une branche tombée lors des grands vents. SVS a sécurisé le soir avec une planche et posé le vitrage 3 jours plus tard. Joints bien faits et appui nickel.",
"Bonne intervention urgence sur une serrure de garage qui ne fonctionnait plus, plus moyen de sortir la voiture. Le serrurier a démonté et changé le bloc en moins dune heure. Tarif vraiment honnête.",
],

# =========================================================================
# 16. Vitrier - Serrurier Soignies - SVS dépannage
# =========================================================================
"Vitrier - Serrurier Soignies - SVS dépannage": [
"Porte palière claquée vers 21h en sortant chercher mes parents qui arrivaient. SVS a envoyé un serrurier en 40 minutes, ouverture sans dégât avec une lame. Tarif annoncé tenu à la facture.",
"Vitre cuisine cassée par un caillou de la tondeuse du voisin, encore une fois. Le vitrier a mesuré dans la journée et posé un nouveau vitrage 4 jours après. Joints bien tirés et appui propre.",
"clé cassée dans la serrure de notre porte d'entrée un samedi soir, panique avant le souper. Le technicien a extrait et remplacé le bloc en moins d'une heure. La clé tourne nickel depuis.",
"Tentative d'effraction sur ma porte palière du 3e, des traces de pince visibles. SVS a posé un cylindre anti-perçage le lendemain matin. La porte est nettement plus solide.",
"Bon dépannage sur un velux brisé par la grêle du printemps. Bâche immédiate le jour même puis vitrage neuf 5 jours plus tard. Plus aucune infiltration dans le grenier.",
"j'ai fait poser une serrure 3 points sur la porte palière de notre appart loué. Le serrurier a tout fait en moins de 2 heures avec un chantier propre. La porte ferme comme un coffre.",
"Cylindre qui forçait depuis l'hiver, ma femme s'inquiétait que je reste bloqué dehors. Le technicien la remplacé par un modèle anti-bumping en moins d'une heure. Plus aucun effort sur la clé.",
"Pose dune nouvelle serrure suite à un déménagement vers Soignies. SVS a remplacé les 2 cylindres en une matinée par des modèles certifiés. Le devis est resté identique à la facture.",
"Vitre baie vitrée fissurée par les écarts thermiques de l'automne. Mesure prise rapidement et pose 5 jours après. La piece est mieux isolée et le bruit a baissé.",
"clé restée à l'intérieur après que ma fille a refermé sans prévenir. Le serrurier a ouvert en moins de 25 minutes avec une lame fine. Tarif weekend vraiment honnête.",
"Suite à un cambriolage chez ma voisine, jai fait poser un cylindre haute sécurité et renforcer la gâche. SVS a tout fait en moins de 2 heures. Je dors enfin tranquille.",
"Intervention sur une serrure de garage qui forçait depuis longtemps, plus moyen de sortir la moto. Le technicien a démonté, nettoyé et remplacé le mécanisme abimé. Plus aucun forçage.",
"Pose d'un verrou supplémentaire sur la porte de service de la maison, modèle à code que j'avais commandé. Le serrurier a fixé proprement en 50 minutes. Aucun jeu.",
"Vitre porte arrière de la maison brisée par une branche tombée pendant la tempête. SVS a sécurisé le soir avec une planche et posé le vitrage 3 jours plus tard. Plus aucune crainte d'intrusion.",
"clé perdue à la piscine de Soignies, j'ai fait changer le cylindre en urgence par sécurité. SVS la remplacé par un modèle certifié en moins d'une heure. Je dors tranquille depuis 3 mois.",
],

# =========================================================================
# 17. Vitrier - Serrurier Nivelles - SVS Dépannage
# =========================================================================
"Vitrier - Serrurier Nivelles - SVS Dépannage": [
"Porte d'entrée claquée en sortant les courses du coffre, mon mari avait l'autre trousseau au boulot. SVS a envoyé quelqu'un en 35 minutes, ouverture rapide sans dégât. Tarif annoncé tenu jusqu'à la facture.",
"Vitre cuisine fracassée par un ballon de foot des enfants dans le jardin. Le vitrier a mesuré dans la journée et posé un nouveau double vitrage 4 jours après. Plus aucun courant d'air.",
"clé cassée dans la serrure de la porte palière de l'appart loué à un de mes locataires. Le serrurier a extrait et remplacé le cylindre en moins d'une heure. Facture conforme au devis téléphonique.",
"Tentative d'effraction sur la porte palière côté Grand Place, traces de pince visibles. SVS a posé un cylindre anti-perçage le lendemain matin. La porte est plus solide qu'avant.",
"Bon dépannage sur un velux brisé par une grosse branche pendant l'orage de mai. Bâche posée le soir et vitrage neuf 5 jours après. Plus aucune trace d'humidité.",
"j'ai fait changer toutes les serrures suite à un divorce, par sécurité. SVS a remplacé 2 cylindres et posé un verrou supplémentaire en une matinée. Le devis a été respecté à l'euro.",
"Cylindre qui forçait depuis longtemps, je devais sortir la clé en 3 essais. Le technicien la remplacé par un modèle anti-bumping en moins d'une heure. Plus aucun effort sur la clé.",
"Pose d'une serrure 3 points sur ma porte palière vieillissante, l'ancienne ne m'inspirait vraiment pas confiance. Le serrurier a tout fait en moins de 2 heures avec un chantier propre. La porte ferme comme un coffre.",
"Intervention au top sur une vitre baie fissurée par les écarts thermiques. Mesure prise rapidement et pose 5 jours après. La piece est plus calme et mieux isolée.",
"Porte d'appart bloquée fermée par un courant d'air, ma fille à l'intérieur avec mon chat. SVS a réagi vite, ouverture en 30 minutes sans toucher au bois. Pas de mauvaise surprise sur la note.",
"clé perdue à la patinoire, jai du faire changer le cylindre en urgence. SVS a remplacé par un modèle certifié et copié 4 clés sur place. Je dors tranquille depuis.",
"Pose d'un blindage discret sur ma porte palière suite à plusieurs effractions dans l'immeuble. Travail propre et discret en un après-midi. Plus aucune crainte d'intrusion.",
"Cylindre forcé par une tentative douverture au tournevis pendant les vacances. SVS la remplacé par un modèle anti-perçage en moins d'une heure et demie. Tarif honnête.",
"Vitre porte arrière de la maison cassée par une chute de pot de fleurs du balcon. Vitrier sur place pour les mesures et pose 4 jours après. Joints bien faits.",
"Bonne intervention urgence sur une serrure 3 points qui ne se verrouillait plus du tout. Le serrurier a démonté et changé deux pignons usés. La porte se ferme nickel maintenant.",
],

# =========================================================================
# 18. Serrurier - Vitrier Wavre - Delta dépannage
# =========================================================================
"Serrurier - Vitrier Wavre - Delta dépannage": [
"Porte d'entrée claquée en sortant chercher mes enfants à l'école, javais oublié les cles dans la cuisine. Delta a envoyé un serrurier en 35 minutes, ouverture sans dégât. Tarif annoncé tenu à la facture.",
"Vitre cuisine cassée par une chute de pot de fleurs du balcon du dessus. Le vitrier Delta a sécurisé le soir et posé un nouveau vitrage 4 jours après. Plus aucun courant d'air.",
"clé cassée dans la serrure de la porte palière dans l'immeuble de l'avenue des Combattants. Le technicien a extrait le bout et remplacé tout le cylindre en moins d'une heure. La clé tourne nickel depuis.",
"Tentative d'effraction sur ma porte palière la nuit, marques de pince visibles le matin. Delta a posé un cylindre anti-perçage le jour même. La porte est nettement plus solide.",
"Bon dépannage sur un velux fendu par la grêle, infiltrations le soir même. Bâche posée immédiatement et vitrage neuf 5 jours après. Plus aucune trace d'humidité dans la chambre.",
"j'ai fait changer toutes les serrures de notre nouvelle maison à Bierges. Delta a remplacé 3 cylindres par des modèles certifiés en une matinée. Le devis a été respecté à l'euro.",
"Cylindre forcé suite à une tentative douverture au tournevis pendant le weekend. Delta la remplacé par un modèle anti-bumping en moins d'une heure et demie. Tarif vraiment honnête.",
"Pose d'une serrure 3 points sur ma porte palière, lancienne ne m'inspirait pas confiance. Le serrurier a tout fait en moins de 2 heures avec un chantier propre. La porte ferme comme un coffre.",
"Vitre baie côté jardin fissurée par les écarts thermiques de l'été. Vitrier sur place pour les mesures et pose 5 jours après. La piece est plus calme et mieux isolée.",
"clé restée à l'intérieur après que ma copine a refermé sans prévenir. Le serrurier a ouvert en moins de 25 minutes avec une lame fine. Tarif weekend vraiment correct.",
"Suite a un cambriolage chez les voisins, on a fait poser un blindage discret et changer le cylindre. Delta a tout fait en un apres-midi sans saletés. Je peux enfin laisser ma femme seule le soir.",
"Cylindre qui forçait depuis longtemps, je sentais quil allait lâcher. Le technicien la remplacé par un modèle certifié en moins d'une heure. Plus aucun effort sur la clé.",
"Intervention sur une serrure de garage qui ne fonctionnait plus, plus moyen de sortir la voiture. Le serrurier a démonté et changé tout le bloc en 1h. Tarif annoncé respecté.",
"Pose d'un verrou supplémentaire sur la porte de service de ma maison, modèle à code. Le technicien a fixé proprement en 50 minutes. Aucun jeu et installation nickel.",
"Vitre porte arrière brisée par une branche tombée lors des grands vents d'automne. Delta a sécurisé le soir et posé le vitrage 3 jours plus tard. Joints bien faits et plus aucune crainte.",
],

# =========================================================================
# 19. Serrurier Liège - Delta Services
# =========================================================================
"Serrurier Liège - Delta Services": [
"Porte d'entrée claquée en sortant au Carré un samedi soir, javais oublié les clés. Delta a envoyé un serrurier en 35 minutes, ouverture sans rayure. Tarif annoncé tenu jusqu'à la facture.",
"Cylindre forcé par une tentative d'effraction sur ma porte palière rue Saint-Gilles. Delta Services a remplacé par un modèle anti-perçage le lendemain matin. La porte est bien plus solide.",
"clé cassée dans la serrure de la cave un soir, le bout coincé empêchait de tourner. Le serrurier a extrait avec un crochet sans démonter et la serrure tourne encore nickel. En 30 minutes c'était plié.",
"Suite à l'achat d'un appart en Outremeuse, on a fait changer toutes les serrures par sécurité. Delta a posé 2 cylindres certifiés et un verrou en une matinée. Le devis a été respecté à l'euro.",
"Bon dépannage suite à une porte palière bloquée fermée à cause du gel sur la gâche. Le technicien Delta a degripé, nettoyé et regraissé. Depuis ça tourne sans accroc même quand il gele.",
"j'ai fait poser une serrure 3 points sur la porte de mon studio à Sainte-Marguerite. Travail soigné en moins de 2 heures avec aspirateur derrière. La porte ferme comme un coffre.",
"Intervention au top sur un cylindre qui grinçait depuis des mois. Le serrurier la démonté, nettoyé et changé deux pignons usés. Plus aucun bruit et clé en douceur.",
"Pose dun blindage discret sur ma porte d'entrée après deux cambriolages dans le quartier. Delta a tout fait en un après-midi sans bruit. Ma femme se sent enfin chez nous.",
"clé perdue à la Batte, jai préféré changer le cylindre par precaution. Delta a remplacé par un modèle à carte de propriété en moins d'une heure et copié 4 clés. Je dors tranquille.",
"Bonne intervention urgence en pleine nuit sur ma porte palière qui ne se verrouillait plus du tout. Le serrurier a réajusté la gâche et regraissé en 40 minutes. Tarif raisonnable.",
"Cylindre forcé par tentative douverture au tournevis pendant que jétais en vacances. Delta la remplacé par un modèle anti-bumping dès mon retour. Pas de mauvaise surprise sur la facture.",
"Pose d'un verrou supplémentaire sur la porte de service de mon studio. Le technicien a aligné et fixé en moins d'une heure. Aucun jeu et installation nickel.",
"Suite a une rupture, jai fait changer toutes les serrures de l'appart pour ma tranquillité. Delta a posé 2 cylindres certifiés en 1h30. Je dors plus tranquille maintenant.",
"clé bloquée dans le cylindre un vendredi soir, plus moyen de tourner. Le serrurier la débloquée et remplacé le bloc usé en moins d'une heure. Facture conforme au devis téléphonique.",
"Intervention sur une serrure de garage qui forçait depuis l'hiver, ma femme n'arrivait plus à sortir la voiture. Le technicien a démonté et changé le mécanisme abimé en moins d'une heure. Plus aucun forçage.",
],

# =========================================================================
# 20. Delta dépannage - Serrurier Liège
# =========================================================================
"Delta dépannage - Serrurier Liège": [
"Porte palière claquée en allant sortir les poubelles, j'étais en chaussons dans le froid. Delta a envoyé un serrurier en 30 minutes, ouverture rapide sans dégât. Tarif vraiment correct.",
"Vitre porte vitrée cassée par une tentative d'intrusion la nuit, sale réveil. Delta a sécurisé avec une planche immédiatement puis posé un nouveau vitrage feuilleté 4 jours après. Plus aucune crainte d'intrusion.",
"clé cassée dans la serrure de la porte de garage, plus moyen de sortir la voiture pour aller bosser. Le serrurier a extrait et changé le cylindre en moins de 50 minutes. Facture matchant le devis téléphonique.",
"Suite a un cambriolage dans la cage d'escalier, jai fais poser un cylindre haute securité. Delta a tout fait le matin meme avec un cornière anti-pince. La porte est nettement plus solide.",
"Bon dépannage un dimanche matin sur ma porte palière qui refusait de se verrouiller. Le technicien Delta a réajusté la gâche et regraissé le mecanisme en moins d'une heure. Tarif weekend honnête.",
"j'ai fait changer toutes les serrures suite à un déménagement vers Cointe. Delta a remplacé 3 cylindres en une matinée par des modèles certifiés. Le devis a été respecté à l'euro près.",
"Pose dune serrure 3 points sur la porte palière de mon appart loué à un étudiant. Travail propre en 2 heures avec un chantier nickel. La porte ferme bien plus solidement.",
"Cylindre qui forçait depuis plusieurs mois, je sentais qu'il allait lâcher. Le serrurier la remplacé par un modèle anti-bumping en moins d'une heure. Plus aucun effort sur la clé.",
"Intervention au top sur une serrure 3 points qui ne verrouillait plus en haut. Le technicien a démonté entièrement et changé deux pignons. La porte ferme comme neuve maintenant.",
"Vitre fenêtre cuisine cassée par un caillou de tondeuse du voisin, classique. Vitrier sur place pour les mesures et pose 5 jours après. Joints bien lisses et appui propre.",
"Bonne intervention urgence en pleine nuit sur une porte palière bloquée fermée par mon ado. Le serrurier a ouvert en moins de 25 minutes. Pas de mauvaise surprise sur la facture.",
"clé perdue à la sortie du métro, jai fais changer le cylindre par sécurité. Delta a remplacé par un modele certifié en moins d'une heure et copié 4 clés. Je dors tranquille depuis.",
"Pose d'un verrou supplémentaire sur ma porte palière, modèle à code commandé en ligne. Le technicien a fixé proprement en 50 minutes. Aucun jeu et installation nickel.",
"Suite à une tentative d'effraction sur la porte d'entrée du commerce, fallait sécuriser vite. Delta a posé un cylindre haute securité et un verrou supplémentaire en une matinée. Plus aucune crainte le soir.",
"Cylindre forcé par tentative douverture au tournevis pendant le weekend. Le serrurier Delta la remplacé par un modèle anti-perçage en moins d'une heure. Tarif vraiment honnête.",
],

# =========================================================================
# 21. Serrurier Herstal - Delta Services
# =========================================================================
"Serrurier Herstal - Delta Services": [
"Porte d'entrée claquée un dimanche matin alors que j'allais chercher le pain, je suis resté en T-shirt dans le froid. Delta a envoyé un serrurier en 35 minutes, ouverture sans dégât. Tarif weekend tout à fait correct.",
"Cylindre forcé suite à une tentative d'effraction sur ma porte palière rue Hayeneux. Delta Services a remplacé par un modèle anti-perçage le lendemain matin. La porte est nettement plus solide.",
"clé cassée dans la serrure de la porte de cave, le bout coincé empêchait de fermer. Le serrurier a extrait sans démonter en moins de 30 minutes. La serrure tourne encore nickel.",
"Suite à l'achat de notre maison à Herstal, on a fait changer toutes les serrures par sécurité. Delta a posé 3 cylindres certifiés en une matinée. Le devis a été respecté à l'euro.",
"Bon dépannage un samedi soir sur ma porte palière bloquée fermée par un courant d'air. Le technicien Delta a réagi vite, ouverture en moins de 30 minutes. Pas de mauvaise surprise.",
"j'ai fait poser une serrure 3 points sur la porte d'entrée de notre maison, plus rassurant pour ma femme. Travail propre en moins de 2 heures avec aspirateur derrière. La porte ferme comme un coffre.",
"Intervention sur un cylindre qui grippait depuis l'hiver, je devais forcer pour ouvrir. Le serrurier la démonté, nettoyé et regraissé. Plus aucun effort sur la clé maintenant.",
"Pose d'un blindage discret sur ma porte palière après des cambriolages dans le voisinage. Delta a tout fait en un après-midi sans bruit ni saletés. Ma femme se sent enfin en sécurité.",
"clé perdue lors d'une sortie dans le parc, jai préféré changer le cylindre par sécurité. Delta a remplacé par un modele à carte de propriété en moins d'une heure et copié 4 cles. Je dors tranquille.",
"Cylindre forcé par une tentative douverture au tournevis pendant que jétais en vacances. Delta la remplacé par un modèle anti-bumping dès mon retour. Tarif vraiment honnête.",
"Porte palière bloquée fermée par mon fils ado un dimanche matin, jétais en pyjama dans le couloir. Le serrurier était sur place en 35 minutes, ouverture sans rayure. Tarif raisonnable.",
"Bonne intervention sur une serrure 3 points qui ne se verrouillait plus en haut. Le technicien a démonté entièrement, changé deux pignons usés et regraissé. La porte ferme comme neuve.",
"Pose d'un verrou supplémentaire sur la porte de service de la maison à la campagne. Delta a percé sans abîmer le chambranle et fixé proprement. Plus aucune crainte d'intrusion par là.",
"Suite a une rupture, jai fais changer toutes les serrures pour ma tranquillité. Delta a posé 2 cylindres certifiés et un verrou en 1h30. Je dors tranquille maintenant.",
"clé bloquée dans le cylindre un vendredi soir en rentrant tard. Le serrurier la débloquée et remplacé le bloc usé en moins d'une heure. Facture conforme au devis téléphonique.",
],

# =========================================================================
# 22. Serrurier Tournai - Delta Services
# =========================================================================
"Serrurier Tournai - Delta Services": [
"Porte d'entrée claquée en sortant chercher du pain rue de Pont, ma femme dormait. Delta a envoyé un serrurier en 35 minutes, ouverture sans dégât. Tarif weekend vraiment correct.",
"Cylindre forcé par une tentative d'effraction sur ma porte palière côté Grand'Place. Delta Services a remplacé par un modèle anti-perçage le lendemain matin. Plus aucune crainte d'intrusion.",
"clé cassée dans la serrure de la porte palière de l'appart loué a un étudiant. Le technicien a extrait et remplacé le bloc en moins d'une heure. Facture conforme au devis téléphonique.",
"Suite à l'achat d'une maison sur l'avenue de Maire, on a fait changer toutes les serrures. Delta a posé 3 cylindres certifiés en une matinée. Le devis n'a pas bougé d'un euro.",
"Bon dépannage un samedi soir sur ma porte palière bloquée par un courant d'air. Le technicien Delta a réagi vite, ouverture en moins de 30 minutes sans rayure. Pas de mauvaise surprise.",
"j'ai fait poser une serrure 3 points sur la porte palière de notre appart, plus rassurant. Travail propre en moins de 2 heures avec aspirateur derrière. La porte ferme nickel.",
"Intervention au top sur un cylindre qui grippait depuis l'hiver. Le serrurier la démonté, nettoyé et regraissé. Plus aucun effort sur la clé depuis 4 mois.",
"Pose d'un blindage discret sur la porte d'entrée après des cambriolages dans le quartier. Delta a tout fait en un après-midi sans bruit. Ma femme respire enfin.",
"clé perdue à la sortie du commerce, j'ai fait changer le cylindre par sécurité. Delta a remplacé par un modèle certifié et copié 4 clés sur place. Je dors tranquille depuis.",
"Cylindre forcé par tentative douverture au tournevis pendant le weekend. Delta la remplacé par un modèle anti-bumping en moins d'une heure et demie. Tarif honnête.",
"Bonne intervention urgence en pleine nuit pour une porte palière qui refusait de se verrouiller. Le serrurier a réajusté la gâche et regraissé en moins de 40 minutes. Tarif raisonnable.",
"Pose d'un verrou supplémentaire sur la porte de service de notre maison à la campagne. Le technicien a fixé proprement en 50 minutes. Aucun jeu.",
"Suite à un déménagement, j'ai fait changer les 2 cylindres de notre nouvel appart. Delta a remplacé en une matinée par des modèles certifiés. Devis respecté.",
"Intervention sur une serrure de garage qui forçait depuis longtemps, plus moyen de sortir la moto. Le serrurier a démonté et changé le mécanisme abimé en moins d'une heure. Plus aucun forçage.",
"clé bloquée dans le cylindre un soir de gel, plus moyen de tourner. Le technicien a debloqué et regraissé le mécanisme. Depuis ça tourne sans accroc même quand il gele.",
],

# =========================================================================
# 23. Serrurier Evere - Expert
# =========================================================================
"Serrurier Evere - Expert": [
"Porte d'entrée claquée en sortant chercher les courses dans la voiture, ma femme dormait avec les clés. Le serrurier était la en 35 minutes, ouverture sans dégât avec une lame. Tarif annoncé tenu à la facture.",
"Cylindre forcé suite à une tentative d'effraction sur ma porte palière chaussée de Louvain. Expert a remplacé par un modèle anti-perçage le lendemain matin. La porte est nettement plus solide.",
"clé cassée dans la serrure de la porte palière, le morceau coincé empêchait dactionner. Le technicien a extrait sans démonter en moins de 30 minutes. La serrure tourne encore nickel.",
"Suite à l'achat d'un appart à Evere, on a fait changer toutes les serrures par sécurité. Expert a posé 2 cylindres certifiés et un verrou en une matinée. Le devis a été respecté à l'euro.",
"Bon dépannage un dimanche matin sur ma porte palière bloquée fermée par un courant d'air. Le serrurier a réagi vite, ouverture en moins de 30 minutes. Pas de mauvaise surprise.",
"j'ai fait poser une serrure 3 points sur la porte d'entrée de mon studio, l'ancienne ne m'inspirait pas confiance. Travail soigné en moins de 2 heures. La porte ferme comme un coffre.",
"Cylindre qui forçait depuis plusieurs mois, ma copine s'inquiétait que je reste bloqué. Le serrurier la remplacé par un modèle anti-bumping en moins d'une heure. Plus aucun effort sur la clé.",
"Intervention au top sur une serrure 3 points qui ne se verrouillait plus en partie haute. Le technicien a démonté entièrement et changé deux pignons usés. La porte ferme comme neuve.",
"Pose dun blindage discret sur ma porte palière après plusieurs effractions dans l'immeuble. Travail propre et discret en un après-midi. Plus aucune crainte d'intrusion.",
"clé perdue dans le tram, jai préféré changer le cylindre par sécurité. Expert a remplacé par un modèle certifié en moins d'une heure et copié 4 clés. Je dors tranquille depuis.",
"Bonne intervention urgence en pleine nuit pour une serrure qui refusait de se verrouiller. Le serrurier a réajusté la gâche et regraissé le mécanisme en 40 minutes. Tarif weekend honnête.",
"Pose d'un verrou supplémentaire sur la porte palière, modèle à code commandé en ligne. Le technicien a fixé proprement en moins d'une heure. Aucun jeu.",
"Cylindre forcé par tentative douverture au tournevis pendant que jétais en vacances. Expert la remplacé par un modele anti-perçage dès mon retour. Pas de mauvaise surprise.",
"Suite à une rupture, jai fait changer toutes les serrures de l'appart pour ma tranquillité. Expert a posé 2 cylindres certifiés en 1h30. Je dors plus tranquille.",
"clé bloquée dans le cylindre un vendredi soir, plus moyen de tourner. Le serrurier la débloquée et remplacé le bloc usé en moins d'une heure. Facture conforme au devis téléphonique.",
],

# =========================================================================
# 24. Serrurier Saint-Paul - Dépannage
# =========================================================================
"Serrurier Saint-Paul - Dépannage": [
"Porte palière claquée en sortant chercher les enfants à l'école, javais oublié les clés à la maison. Le serrurier était sur place en 35 minutes, ouverture sans dégât. Tarif annoncé tenu à la facture.",
"Cylindre forcé suite à une tentative d'effraction sur ma porte palière, des traces de pince visibles. Saint-Paul a remplacé par un modèle anti-perçage le lendemain matin. La porte est nettement plus solide.",
"clé cassée dans la serrure de la porte d'entrée un vendredi soir, panique avant le souper familial. Le technicien a extrait le bout et changé le cylindre en moins d'une heure. La clé tourne nickel depuis.",
"Suite à l'achat de notre maison, on a fait changer toutes les serrures par sécurité. Saint-Paul a posé 3 cylindres certifiés en une matinée. Le devis a été respecté à l'euro.",
"Bon dépannage un dimanche matin sur ma porte palière bloquée fermée par un courant d'air. Le serrurier a réagi vite, ouverture en moins de 30 minutes. Pas de mauvaise surprise.",
"j'ai fait poser une serrure 3 points sur la porte palière de mon studio loué à un étudiant. Travail propre en moins de 2 heures avec un chantier nickel. La porte ferme comme un coffre.",
"Cylindre qui forçait depuis l'hiver, jentendais le mécanisme grincer. Le technicien la remplacé par un modèle anti-bumping en moins d'une heure. Plus aucun effort sur la clé.",
"Pose dun blindage discret sur ma porte palière suite a deux cambriolages dans le batiment. Travail propre et discret en un apres-midi. Je peux laisser ma femme seule le soir tranquille.",
"clé perdue lors d'une sortie en ville, jai préféré changer le cylindre par sécurité. Saint-Paul a remplacé par un modele à carte de propriété en moins d'une heure et copié 4 clés. Je dors tranquille.",
"Cylindre forcé par tentative douverture au tournevis pendant que jétais en vacances. Le serrurier la remplacé par un modèle anti-perçage dès mon retour. Tarif vraiment honnête.",
"Bonne intervention urgence en pleine nuit pour une serrure qui refusait obstinément de se verrouiller. Le technicien a réajusté la gâche et regraissé en 40 minutes. Tarif weekend honnête.",
"Pose d'un verrou supplémentaire sur la porte de service de notre maison à la campagne. Le serrurier a aligné et fixé proprement en 50 minutes. Aucun jeu.",
"Suite à une rupture, j'ai fait changer toutes les serrures de l'appart pour ma tranquillité. Saint-Paul a posé 2 cylindres certifiés et un verrou en 1h30. Je dors plus tranquille.",
"Intervention sur une serrure de garage qui ne fonctionnait plus, plus moyen de sortir la voiture. Le technicien a démonté et changé le bloc en moins d'une heure. Plus aucun forçage.",
"clé bloquée dans le cylindre un soir de gel, plus moyen de tourner. Le serrurier la débloquée et regraissé le mécanisme. Depuis ça tourne sans accroc même quand il gele.",
],

# =========================================================================
# 25. Top Serrures & vitres express - Enghien
# =========================================================================
"Top Serrures & vitres express -Enghien": [
"Porte d'entrée claquée en sortant fermer le portail du jardin, ma femme dormait à l'étage. Le serrurier était la en 30 minutes, ouverture sans dégât avec une lame. Tarif vraiment correct.",
"Vitre fenêtre salle à manger fracassée par un coup de balle des enfants du voisin. Le vitrier a mesuré dans la journée et posé un nouveau double vitrage 4 jours après. Plus aucun courant d'air.",
"clé cassée dans la serrure de la porte palière, je rentrais du boulot fatigué. Le technicien a extrait le morceau et remplacé le bloc en moins d'une heure. La clé tourne nickel depuis.",
"Tentative d'effraction sur la porte palière côté place du Vieux Marché, traces de pince visibles. Top Serrures a posé un cylindre anti-perçage le lendemain matin. La porte est plus solide.",
"Bon dépannage sur un velux brisé par la grêle du printemps. Bâche immédiate posée le soir et vitrage neuf 5 jours après. Plus aucune trace d'humidité dans le grenier.",
"j'ai fait changer toutes les serrures de notre nouvelle maison à Enghien. Trois cylindres certifiés posés en moins de 2 heures par des modèles haut de gamme. Le devis a été respecté à l'euro.",
"Cylindre qui forçait depuis plusieurs mois, je sentais quil allait lâcher. Le serrurier la remplacé par un modèle anti-bumping en moins d'une heure. Plus aucun effort sur la clé.",
"Pose dune serrure 3 points sur la porte palière du bureau qu'on loue dans le centre. Travail propre en 2 heures avec chantier nickel. La porte ferme comme un coffre.",
"Vitre baie cassée par une chute de branche pendant la tempête, fallait sécuriser vite. Vitrier sur place dans la matinée et pose du nouveau vitrage 5 jours après. Joints bien lisses.",
"clé perdue lors d'une promenade dans le parc, jai préféré changer le cylindre par sécurité. Top Serrures a remplacé par un modèle certifié en moins d'une heure et copié 4 clés. Je dors tranquille.",
"Porte d'appart bloquée fermée par mon fils ado, j'étais dans le couloir avec les courses. Intervention en 35 minutes, ouverture sans rayure. Pas de mauvaise surprise sur la facture.",
"Pose d'un blindage discret sur ma porte palière après des cambriolages dans le quartier. Travail propre et discret en un après-midi. Ma femme se sent enfin chez nous.",
"Vitre porte arrière de la maison brisée par une branche tombée lors des grands vents. Top Serrures a sécurisé le soir et posé le vitrage 3 jours plus tard. Plus aucune crainte d'intrusion.",
"Bonne intervention urgence sur une serrure 3 points qui ne se verrouillait plus en partie haute. Le technicien a démonté et changé deux pignons usés. La porte ferme comme neuve.",
"Cylindre forcé par tentative douverture au tournevis pendant le weekend. Top Serrures la remplacé par un modèle anti-perçage en moins d'une heure et demie. Tarif vraiment honnête.",
],

# =========================================================================
# 26. Serrurier - Vitrier Braine l'Alleud - SVS dépannage
# =========================================================================
"Serrurier - Vitrier Braine l'Alleud - SVS dépannage": [
"Porte d'entrée claquée vers 22h en sortant promener le chien rue Pierre Flamand, javais oublié les cles. SVS a envoyé un serrurier en 40 minutes, ouverture sans dégât. Tarif annoncé tenu à la facture.",
"Vitre porte vitrée arrière fracassée par une tentative d'intrusion pendant la nuit, sale réveil. SVS a sécurisé immédiatement par planche puis posé un vitrage feuilleté 4 jours après. Plus aucune crainte d'intrusion.",
"clé cassée dans la serrure de la porte palière du 2e étage, je rentrais des courses. Le technicien a extrait le bout et remplacé le bloc en moins d'une heure. La clé tourne nickel depuis.",
"Tentative d'effraction sur la porte palière, marques de pince visibles le matin au réveil. SVS a posé un cylindre anti-perçage et renforcé la gâche le jour même. La porte est nettement plus solide.",
"Bon dépannage sur un velux brisé par la grêle du printemps, infiltrations dans le grenier. Bâche posée le soir et vitrage neuf 5 jours après. Plus aucune trace d'humidité au plafond.",
"j'ai fait changer toutes les serrures suite à un emménagement à Braine. SVS a remplacé 3 cylindres par des modèles certifiés en une matinée. Le devis a été respecté à l'euro.",
"Cylindre qui forçait depuis longtemps, ma femme s'inquiétait que je reste bloqué dehors. Le serrurier la remplacé par un modèle anti-bumping en moins d'une heure. Plus aucun effort sur la clé.",
"Pose d'une serrure 3 points sur la porte palière de notre appart loué, plus rassurant pour les locataires. Travail propre en 2 heures avec aspirateur derrière. La porte ferme comme un coffre.",
"Vitre baie côté jardin fissurée par les écarts thermiques de l'automne. Vitrier sur place pour les mesures et pose 5 jours après. La piece est plus calme et mieux isolée maintenant.",
"clé perdue lors d'une sortie dans le parc, j'ai préféré changer le cylindre par sécurité. SVS a remplacé par un modèle à carte de propriété en moins d'une heure. Je dors tranquille depuis.",
"Porte d'appart bloquée fermée par un courant d'air, ma fille à l'intérieur avec le chat. SVS a réagi vite, ouverture en 30 minutes sans toucher au bois. Pas de mauvaise surprise.",
"Pose dun blindage discret sur la porte d'entrée après deux cambriolages dans le quartier. Travail propre et discret en un après-midi. Plus aucune crainte d'intrusion.",
"Cylindre forcé par tentative douverture au tournevis pendant les vacances. SVS la remplacé par un modèle anti-perçage dès notre retour. Tarif vraiment honnête.",
"Vitre porte arrière brisée par une branche tombée lors des grands vents d'automne. SVS a sécurisé le soir par planche et posé le vitrage 3 jours après. Joints bien faits et appui nickel.",
"Bonne intervention urgence sur une serrure de garage qui ne fonctionnait plus, plus moyen de sortir la voiture. Le serrurier a démonté et changé le bloc en moins d'une heure. Plus aucun forçage.",
],

# =========================================================================
# 27. Vitrier - Serrurier Ottignies - SVS dépannage
# =========================================================================
"Vitrier - Serrurier Ottignies - SVS dépannage": [
"Porte d'entrée claquée en sortant chercher du pain rue de la Gare, ma femme dormait. SVS a envoyé un serrurier en 35 minutes, ouverture sans dégât avec une lame fine. Tarif annoncé tenu jusqu'à la facture.",
"Vitre cuisine cassée par un caillou de tondeuse du jardin voisin. Le vitrier a mesuré dans la journée et posé un nouveau double vitrage 4 jours plus tard. Joints bien lisses.",
"clé cassée dans la serrure de la porte palière de l'appart au campus, je rentrais d'un examen. Le technicien a extrait le bout et changé le bloc en moins d'une heure. La clé tourne nickel.",
"Tentative d'effraction sur la porte d'entrée de notre maison, traces de pince visibles. SVS a posé un cylindre anti-perçage le lendemain matin. La porte est nettement plus solide.",
"Bon dépannage sur un velux brisé par la grêle de mars. Bâche immédiate posée le soir et vitrage neuf 5 jours plus tard. Plus aucune infiltration dans le grenier.",
"j'ai fait changer toutes les serrures après un emménagement vers le centre d'Ottignies. SVS a posé 3 cylindres certifiés en une matinée. Le devis n'a pas bougé d'un euro.",
"Cylindre qui forçait depuis l'hiver, je devais sortir la clé en plusieurs essais. Le serrurier la remplacé par un modèle anti-bumping en moins d'une heure. Plus aucun effort sur la clé.",
"Pose d'une serrure 3 points sur la porte palière de mon kot loué à des étudiants. Travail propre en moins de 2 heures avec chantier nickel. La porte ferme comme un coffre.",
"Vitre baie côté jardin fissurée par les écarts thermiques. Vitrier sur place pour les mesures et pose 5 jours après. La piece est plus calme et mieux isolée.",
"clé perdue dans le bus, j'ai préféré changer le cylindre par sécurité. SVS a remplacé par un modèle certifié en moins d'une heure et copié 4 clés. Je dors tranquille depuis.",
"Porte d'appart bloquée fermée par un courant d'air, mon colocataire à l'intérieur. SVS a réagi vite, ouverture en 30 minutes sans toucher au bois. Pas de mauvaise surprise sur la facture.",
"Pose d'un blindage discret sur la porte d'entrée après plusieurs cambriolages dans la résidence. Travail propre et discret en un après-midi. Plus aucune crainte d'intrusion.",
"Cylindre forcé par tentative douverture au tournevis pendant le weekend. SVS la remplacé par un modele anti-perçage en moins d'une heure et demie. Tarif vraiment honnête.",
"Vitre porte arrière brisée par une branche tombée lors d'une tempête. SVS a sécurisé le soir avec une planche et posé le vitrage 3 jours après. Joints bien faits.",
"Bonne intervention urgence en pleine nuit sur une serrure 3 points qui ne se verrouillait plus en haut. Le technicien a démonté entièrement et changé deux pignons usés. La porte ferme comme neuve.",
],

# =========================================================================
# 28. SL Débouchage - Bruxelles (Plumber)
# =========================================================================
"SL Débouchage - Bruxelles": [
"WC complètement bouché un dimanche matin avec la famille à la maison, panique totale. SL a envoyé un technicien en 45 minutes, débouchage à la pompe puis ressort en 30 minutes. L'évacuation est nickel depuis.",
"Évier de cuisine qui n'évacuait plus du tout, l'eau stagnait pendant des heures. Le plombier a passé le furet et identifié un bouchon de graisse en moins de 40 minutes. Plus aucun ralentissement depuis 3 mois.",
"Bon dépannage suite à un refoulement dans la cave avec des odeurs vraiment désagréables. Inspection à la caméra puis curage du collecteur principal en une matinée. Plus aucune odeur même quand il pleut fort.",
"j'avais une douche qui se vidait au ralenti depuis des semaines, ya des cheveux et du calcaire selon le technicien. SL a démonté le siphon, curé puis remonté en moins d'une heure. L'eau s'écoule nickel depuis.",
"Canalisation principale bouchée par des lingettes des enfants, refoulement dans le rez-de-chaussée. Intervention en moins d'une heure avec curage haute pression. Plus aucun ralentissement et facture conforme au devis.",
"Suite à des odeurs persistantes dans la salle de bain, jai appelé SL pour une inspection caméra. Diagnostic clair sur un bouchon de cheveux dans le coude, ils l'ont retiré dans la foulée. Plus aucune odeur depuis.",
"Baignoire qui se vidait très lentement, ma femme en avait marre. Le plombier a démonté le siphon, retiré une boule de cheveux et de savon. L'eau s'écoule en quelques minutes maintenant.",
"WC bouché en pleine soirée un samedi, classique apres un repas familial. SL a debarqué en 40 minutes, debouchage en 25 minutes avec une ventouse pro et un furet. Tarif weekend honnête.",
"Inspection caméra dans nos canalisations après un achat de maison, on voulait vérifier l'état. Diagnostic clair sur des racines d'arbre dans le collecteur. Curage et traitement effectués en une matinée.",
"Évacuation extérieure du garage bouchée par des feuilles mortes, leau remontait dans la cave. Le technicien a curé tout en moins d'une heure avec un débouchage haute pression. Plus aucun retour d'eau depuis.",
"Bon dépannage sur un évier de salle de bain qui n'évacuait plus du tout. Démontage du siphon et passage du furet en moins de 30 minutes. Le plombier a tout nettoyé derrière.",
"Suite à un dégat des eaux dans la cave, jai appelé SL pour identifier le bouchon dans le collecteur. Caméra puis curage haute pression en une matinée. Plus aucune crainte de retour d'eau.",
"WC qui se bouchait régulièrement depuis quelques semaines, je devais utiliser la ventouse a chaque fois. SL a identifié un problème de pente, débouché et conseillé. Plus aucun bouchon depuis 4 mois.",
"Canalisation cuisine bouchée par de la graisse accumulée, l'eau remontait dans l'évier. Intervention en moins d'une heure avec un débouchage mécanique puis hydrocurage. Tarif annoncé respecté.",
"Refoulement dans la douche un vendredi soir, je rentrais du boulot. Le plombier était la en 50 minutes, identifié un bouchon dans la verticale et tout curé. L'eau s'écoule nickel depuis.",
],

# =========================================================================
# 29. SL Débouchage – Waterloo (Plumber)
# =========================================================================
"SL Débouchage – Waterloo": [
"WC bouché un dimanche matin avec la belle-famille qui devait arriver. SL a envoyé un technicien en 40 minutes, débouchage avec un furet en moins de 30 minutes. L'évacuation est nickel depuis.",
"Évier cuisine bouché par de la graisse, l'eau stagnait depuis 2 jours. Le plombier a démonté le siphon, identifié le bouchon et tout curé en moins de 40 minutes. Plus aucun ralentissement.",
"Bon dépannage suite à un refoulement dans la cave avec odeurs vraiment désagreables. Inspection caméra puis curage haute pression du collecteur en une matinée. Plus aucune odeur depuis.",
"j'avais une douche qui se vidait au ralenti depuis des semaines, jusqu'à stagner complétement. SL a démonté le siphon, retiré une boule de cheveux et tout nettoyé en moins d'une heure. L'eau s'écoule nickel.",
"Canalisation principale bouchée par des lingettes, refoulement dans la cuisine. Intervention en moins d'une heure avec curage haute pression. Plus aucun ralentissement depuis et facture matchant le devis.",
"Suite à des odeurs persistantes dans la salle de bain, jai appelé SL pour une inspection caméra. Diagnostic clair sur un bouchon de cheveux. Curage immédiat et plus aucune odeur depuis.",
"Baignoire qui se vidait très lentement, javais essayé tous les produits sans succès. Le plombier a demonte le siphon, retiré une boule de cheveux et de savon. L'eau s'écoule rapidement maintenant.",
"WC bouche en pleine soirée un samedi apres un souper familial. SL a debarqué en 40 minutes, debouchage en 25 minutes avec ventouse pro. Tarif weekend honnete.",
"Inspection caméra dans nos canalisations après l'achat d'une maison sur la chaussée de Bruxelles. Diagnostic clair sur des racines dans le collecteur. Curage et traitement en une matinée.",
"Évacuation extérieure du garage bouchée par des feuilles, l'eau remontait dans la cave. Le technicien a curé en moins d'une heure avec un débouchage haute pression. Plus aucun retour d'eau.",
"Bon dépannage sur un évier salle de bain qui n'évacuait plus. Démontage du siphon et passage du furet en moins de 30 minutes. Le plombier a tout nettoyé derrière proprement.",
"Suite à un dégat des eaux dans la cave, jai appelé SL pour identifier le bouchon. Caméra puis curage haute pression en une matinée. Plus aucune crainte de retour d'eau depuis.",
"WC qui se bouchait régulièrement depuis quelques semaines, j'utilisais la ventouse a chaque fois. SL a identifié un problème de pente et débouché. Plus aucun bouchon depuis 4 mois.",
"Canalisation cuisine bouchée par de la graisse, l'eau remontait dans l'évier. Intervention en moins d'une heure avec un débouchage mécanique puis hydrocurage. Tarif annoncé respecté.",
"Refoulement dans la douche un vendredi soir en rentrant du boulot. Le plombier était la en 50 minutes, identifié un bouchon dans la verticale et tout curé. L'eau s'écoule nickel depuis.",
],

# =========================================================================
# 30. Vitrier - Serrurier Mons - SVS dépannage
# =========================================================================
"Vitrier - Serrurier Mons - SVS dépannage": [
"Porte d'entrée claquée en sortant chercher mes enfants au foot, javais oublié mes cles sur la commode. SVS a envoyé un serrurier en 35 minutes, ouverture sans dégât. Tarif annoncé tenu à la facture.",
"Vitre cuisine cassée par un coup de ballon de mes enfants dans le jardin. Le vitrier a mesuré dans la journée et posé un nouveau double vitrage 4 jours plus tard. Joints bien lisses et appui propre.",
"clé cassée dans la serrure de la porte palière côté Grand-Place, je rentrais du boulot fatigué. Le technicien a extrait le bout et changé le bloc en moins d'une heure. La clé tourne nickel depuis.",
"Tentative d'effraction sur la porte d'entrée de notre maison, traces de pince visibles. SVS a posé un cylindre anti-perçage et renforcé la gâche le lendemain matin. La porte est nettement plus solide.",
"Bon dépannage sur un velux brisé par la grêle du printemps, infiltrations dans le grenier. Bâche immédiate posée le soir et vitrage neuf 5 jours après. Plus aucune trace d'humidité au plafond.",
"j'ai fait changer toutes les serrures après emménagement dans notre maison à Mons. SVS a posé 3 cylindres certifiés en une matinée. Le devis n'a pas bougé d'un euro.",
"Cylindre qui forçait depuis l'hiver, je sentais quil allait lâcher. Le serrurier la remplacé par un modèle anti-bumping en moins d'une heure. Plus aucun effort sur la clé.",
"Pose dune serrure 3 points sur la porte palière de mon studio loué à un étudiant. Travail propre en moins de 2 heures avec chantier nickel. La porte ferme comme un coffre.",
"Vitre baie côté terrasse fissurée par les écarts thermiques. Vitrier sur place pour les mesures et pose 5 jours plus tard. La piece est plus calme et mieux isolée.",
"clé perdue lors d'une sortie en ville, jai préféré changer le cylindre par sécurité. SVS a remplacé par un modèle à carte de propriété en moins d'une heure. Je dors tranquille depuis.",
"Porte d'appart bloquée fermée par un courant d'air, ma fille à l'intérieur avec le chat. SVS a réagi vite, ouverture en 30 minutes sans toucher au bois. Pas de mauvaise surprise.",
"Pose d'un blindage discret sur ma porte palière après plusieurs cambriolages dans le voisinage. Travail propre et discret en un après-midi. Plus aucune crainte d'intrusion par là.",
"Cylindre forcé par tentative douverture au tournevis pendant le weekend. SVS la remplacé par un modele anti-perçage en moins d'une heure et demie. Tarif vraiment honnête.",
"Vitre porte arrière brisée par une branche tombée lors des grands vents. SVS a sécurisé le soir avec une planche et posé le vitrage 3 jours après. Joints bien faits.",
"Bonne intervention urgence sur une serrure de garage qui ne fonctionnait plus, plus moyen de sortir la voiture. Le serrurier a démonté et changé le bloc en moins d'une heure. Plus aucun forçage.",
],

}

# ============================================================================
# Write to sheet
# ============================================================================
def main():
    gs = GSheet(SHEET_ID)
    existing_tabs = set(gs.list_sheets())

    total_written = 0
    for tab_name, reviews in REVIEWS.items():
        if tab_name not in existing_tabs:
            print(f"  [SKIP] Tab not found: {tab_name}")
            continue
        if len(reviews) != 15:
            print(f"  [WARN] {tab_name} has {len(reviews)} reviews (expected 15)")

        # # column A11:A25 ; reviews column C11:C25
        nums = [[i + 1] for i in range(len(reviews))]
        texts = [[r] for r in reviews]

        try:
            gs.update(tab_name, f"A11:A{10 + len(reviews)}", nums)
            gs.update(tab_name, f"C11:C{10 + len(reviews)}", texts)
            total_written += len(reviews)
            print(f"  [OK]   {tab_name}: {len(reviews)} reviews written")
            time.sleep(0.4)  # be gentle with the API
        except Exception as e:
            print(f"  [ERR]  {tab_name}: {e}")

    print(f"\nDone. Total reviews written: {total_written}")

if __name__ == "__main__":
    main()
