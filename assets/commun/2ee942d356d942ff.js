(function ortCountryLink(folders){
  var lang=(document.documentElement.lang||'fr').slice(0,2), folder=folders[lang]||folders.en, dataPromise, last='';
  var labels={fr:['Voir l’autre itinéraire sur ce pays','Voir les {n} autres itinéraires sur ce pays'],en:['See the other itinerary in this country','See {n} other itineraries in this country'],es:['Ver el otro itinerario de este país','Ver los otros {n} itinerarios de este país'],it:['Scopri l’altro itinerario in questo paese','Scopri gli altri {n} itinerari in questo paese'],pt:['Ver o outro itinerário neste país','Ver os outros {n} itinerários neste país'],de:['Weitere Reiseroute in diesem Land ansehen','{n} weitere Reiserouten in diesem Land ansehen'],nl:['Bekijk de andere reisroute in dit land','Bekijk de {n} andere reisroutes in dit land'],ar:['شاهد المسار الآخر في هذا البلد','شاهد {n} مسارات أخرى في هذا البلد']};
  // Le style peut deja etre dans la page (lien pose a la construction) : pas de doublon.
  var style=document.getElementById('ortCountryLinkCss')||document.createElement('style');
  if(!style.id)style.textContent='.ort-country-link{display:block;padding:18px 22px;background:#fff3c4;color:#123f76!important;border:2px solid #efa900;border-radius:10px;font:700 18px/1.4 system-ui,sans-serif;text-decoration:none!important;box-shadow:0 3px 12px #0002;text-align:center;box-sizing:border-box}.ort-country-link:hover{background:#ffe59a}.ort-country-link:focus-visible{outline:3px solid #123f76;outline-offset:3px}.ort-country-rail .t30-sl{height:420px}.ort-country-rail .ort-country-link{margin-bottom:16px}body.t30 .hc>.ort-country-rail{grid-column:2;grid-row:1/span 12;align-self:stretch}.ort-country-host{position:relative;padding-inline-end:350px!important}.ort-country-host>.ort-country-link{position:absolute;inset-inline-end:24px;bottom:16px;width:300px;z-index:3}@media(max-width:900px){.ort-country-host{padding-inline-end:16px!important}.ort-country-host>.ort-country-link{position:static;width:auto;margin-top:16px}body.t30 .hc>.ort-country-rail{grid-column:1;grid-row:auto}.ort-country-rail .t30-sl{display:none}.ort-country-rail .ort-country-link{margin:16px 0}}';
  if(!style.parentNode)document.head.appendChild(style);
  function update(){
    var cc=(document.body.dataset.cc||'').toUpperCase();
    if(!/^[A-Z]{2}$/.test(cc)||cc===last)return;
    last=cc;
    if(!dataPromise)dataPromise=fetch('/'+folder+'/index-data.json').then(function(r){if(!r.ok)throw Error('catalog');return r.json();});
    dataPromise.then(function(data){
      if(last!==cc||!Array.isArray(data))return;
      var slug=decodeURIComponent(location.pathname.split('/').pop()).replace(/\.html$/,'');
      var seen=new Set();data.forEach(function(it){if(String(it.cc||'').toUpperCase()===cc&&!it.prive&&it.slug&&it.slug!==slug)seen.add(it.slug);});
      var a=document.getElementById('ortCountryLink');
      if(!seen.size){if(a)a.remove();return;}
      // Lien deja en place (pose a la construction) : on corrige seulement le texte, sans le deplacer.
      var placed=!!a;
      if(!a){a=document.createElement('a');a.id='ortCountryLink';a.className='ort-country-link';}
      a.textContent=(labels[lang]||labels.en)[seen.size===1?0:1].replace('{n}',seen.size)+' →';
      a.href='/index.html?lang='+encodeURIComponent(lang)+'&sort=country&country='+cc+'#country-'+cc;
      if(placed)return;
      var hc=document.querySelector('.hr .hc'),photo=document.getElementById('t30Sl'),flowRail=document.getElementById('t30Rail');
      // Page qui defile d'un bloc : le lien va toujours en tete de la colonne de droite.
      if(flowRail){flowRail.prepend(a);}
      else if(document.body.classList.contains('t30')&&photo){
        var rail=photo.parentElement;
        if(!rail.classList.contains('ort-country-rail')){rail=document.createElement('div');rail.className='ort-country-rail';photo.before(rail);rail.appendChild(photo);}
        rail.prepend(a);
      }else if(hc){hc.classList.add('ort-country-host');hc.appendChild(a);}
      else {var text=document.getElementById('textPanel');if(text)text.prepend(a);}
    }).catch(function(){/* Aucun compteur inventé si le catalogue est indisponible. */});
  }
  new MutationObserver(update).observe(document.body,{attributes:true,attributeFilter:['data-cc']});
  // Le catalogue (lourd) se charge une fois la page affichee, sans ralentir l'ouverture.
  function later(){if(window.requestIdleCallback)requestIdleCallback(update,{timeout:4000});else setTimeout(update,2500);}
  if(document.readyState==='complete')later();else window.addEventListener('load',later,{once:true});
})({"fr":"itineraires","en":"itineraries","es":"rutas","pt":"roteiros","it":"itinerari","ar":"masar","nl":"routes","de":"routen"});