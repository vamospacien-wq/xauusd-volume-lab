/* Wyckoff range research module — heuristic screening, not trade advice. */
(()=>{'use strict';
const mean=a=>a.length?a.reduce((s,x)=>s+x,0)/a.length:0;
function atr(bars,i,n){let a=[];for(let k=Math.max(1,i-n+1);k<=i;k++){const b=bars[k],p=bars[k-1];a.push(Math.max(b.high-b.low,Math.abs(b.high-p.close),Math.abs(b.low-p.close)))}return mean(a)}
function analyze(bars,opt={}){
 const n=Math.max(20,Math.min(120,Number(opt.rangeWindow)||40)),volMult=Number(opt.volumeMultiple)||1.5;
 const events=[],ranges=[];let lastEnd=-1;
 for(let i=n+14;i<bars.length-12;i++){
  const w=bars.slice(i-n,i),hi=Math.max(...w.map(x=>x.high)),lo=Math.min(...w.map(x=>x.low)),mid=(hi+lo)/2,atrNow=atr(bars,i,14),width=hi-lo;
  if(!(atrNow>0)||width>atrNow*8)continue;
  const net=Math.abs(w[w.length-1].close-w[0].open),eff=net/width;
  if(eff>.48)continue;
  const prior=bars.slice(Math.max(0,i-n*2),i-n),priorNet=prior.length?prior[prior.length-1].close-prior[0].open:0;
  const trendThreshold=atrNow*2;
  const bias=priorNet>trendThreshold?'after_advance':priorNet< -trendThreshold?'after_decline':'neutral';
  const b=bars[i],avgVol=mean(w.slice(-20).map(x=>x.volume).filter(x=>x>0)),volRatio=avgVol>0?b.volume/avgVol:0;
  const spring=b.low<lo-atrNow*.05&&b.close>lo&&b.close<mid;
  const utad=b.high>hi+atrNow*.05&&b.close<hi&&b.close>mid;
  const reclaimUp=bars.slice(i+1,i+4).some(x=>x.close>lo+width*.25);
  const reclaimDown=bars.slice(i+1,i+4).some(x=>x.close<hi-width*.25);
  let type='Indeterminado',event='Rango sin evento confirmado',confidence='Baja';
  if(spring&&reclaimUp&&volRatio>=volMult){type='Posible acumulación';event='Spring con recuperación';confidence='Media'}
  else if(utad&&reclaimDown&&volRatio>=volMult){type='Posible distribución';event='UTAD con rechazo';confidence='Media'}
  else if(bias==='after_decline'&&b.close>mid&&volRatio>=1.2){type='Sesgo de acumulación';event='Reacción desde zona baja';confidence='Baja'}
  else if(bias==='after_advance'&&b.close<mid&&volRatio>=1.2){type='Sesgo de distribución';event='Reacción desde zona alta';confidence='Baja'}
  const key=Math.floor(i/Math.max(5,Math.floor(n/3)));
  if(i-lastEnd<n/3)continue;
  const future=[1,3,5,10].map(h=>{const f=bars[i+h];return f?{h,change:f.close-b.close,rangeAtr:(f.close-b.close)/atrNow}:null}).filter(Boolean);
  ranges.push({index:i,from:i-n,to:i-1,high:hi,low:lo,width,atr:atrNow,bias,type,event,confidence,volumeRatio:volRatio,future});
  if(type!=='Indeterminado'){events.push(ranges[ranges.length-1]);lastEnd=i}
 }
 const counts={ranges:ranges.length,accumulation:events.filter(x=>x.type.toLowerCase().includes('acumulación')).length,distribution:events.filter(x=>x.type.toLowerCase().includes('distribución')).length,indeterminate:ranges.filter(x=>x.type==='Indeterminado').length};
 return {ranges,events,counts,settings:{rangeWindow:n,volumeMultiple:volMult},note:'Detección heurística experimental. Un rango y un evento Wyckoff requieren validación visual; no genera órdenes.'};
}
window.WyckoffRangeResearch={analyze};
})();