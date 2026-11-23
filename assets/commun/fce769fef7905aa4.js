(function(){
  var box=document.getElementById("ortCostBox");
  var boxM=document.getElementById("ortCostBoxModal");
  if(!box&&!boxM)return;
  var pill=document.getElementById("pill-cost");
  var cc=(document.body.getAttribute("data-cc")||"").toUpperCase();
  var lang=(document.documentElement.lang||"en").slice(0,2);
  var L={
    fr:{o:"Coût global",a:"Hébergement",f:"Restauration",tr:"Transport",ac:"Activités",src:"Échelle relative de 1 à 5. Source : Numbeo / BudgetYourTrip."},
    en:{o:"Overall cost",a:"Accommodation",f:"Food",tr:"Transport",ac:"Activities",src:"Relative scale from 1 to 5. Source: Numbeo / BudgetYourTrip."},
    es:{o:"Coste general",a:"Alojamiento",f:"Comida",tr:"Transporte",ac:"Actividades",src:"Escala relativa de 1 a 5. Fuente: Numbeo / BudgetYourTrip."},
    pt:{o:"Custo geral",a:"Alojamento",f:"Alimentação",tr:"Transporte",ac:"Atividades",src:"Escala relativa de 1 a 5. Fonte: Numbeo / BudgetYourTrip."},
    it:{o:"Costo generale",a:"Alloggio",f:"Ristorazione",tr:"Trasporti",ac:"Attività",src:"Scala relativa da 1 a 5. Fonte: Numbeo / BudgetYourTrip."},
    ar:{o:"التكلفة الإجمالية",a:"الإقامة",f:"الطعام",tr:"النقل",ac:"الأنشطة",src:"مقياس نسبي من 1 إلى 5. المصدر: Numbeo / BudgetYourTrip."},
    nl:{o:"Totale kosten",a:"Accommodatie",f:"Eten en drinken",tr:"Vervoer",ac:"Activiteiten",src:"Relatieve schaal van 1 tot 5. Bron: Numbeo / BudgetYourTrip."},
    de:{o:"Gesamtkosten",a:"Unterkunft",f:"Verpflegung",tr:"Transport",ac:"Aktivitäten",src:"Relative Skala von 1 bis 5. Quelle: Numbeo / BudgetYourTrip."},
  };
  var T=L[lang]||L.en;
  fetch("/data/Roadtripsprefabriques/countries/countries_cost_index.json").then(function(r){return r.ok?r.json():null;}).then(function(d){
    if(!d||!d.countries){if(pill)pill.style.display="none";return;}
    var c=d.countries.filter(function(x){return (x.country_code||"").toUpperCase()===cc;})[0];
    if(!c||!c.cost_ratings){if(pill)pill.style.display="none";return;}
    var cr=c.cost_ratings;
    var rows=[["overall",T.o],["accommodation",T.a],["food",T.f],["transport",T.tr],["activities",T.ac]];
    var html="";
    rows.forEach(function(rw){
      var v=cr[rw[0]];if(!v)return;
      var n=Math.max(0,Math.min(5,v));var dots="";
      for(var i=0;i<5;i++){dots+=(i<n?"\u25cf":"\u25cb");}
      html+="<div class=\"oc-row\"><span class=\"oc-lbl\">"+rw[1]+"</span><span class=\"oc-dots\">"+dots+"</span><span class=\"oc-score\">"+n+"/5</span></div>";
    });
    if(!html){if(pill)pill.style.display="none";return;}
    html+="<div class=\"oc-src\">"+T.src+"</div>";
    if(box)box.innerHTML=html;
    if(boxM)boxM.innerHTML=html;
  }).catch(function(){if(pill)pill.style.display="none";});
})();