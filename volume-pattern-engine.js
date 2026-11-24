/* XAUUSD Volume Lab — individual prior-candle divergence research.
 * Candidate volume is compared separately with each prior candle having a larger
 * full high-to-low range. No average-volume threshold and no requirement to be
 * the largest volume in the comparison window.
 */
(function(root){"use strict";
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
function analyze(bars,options){
 const o=options||{},lookback=clamp(Math.floor(Number(o.lookback)||5),3,7),rangePct=clamp(Number(o.rangeSmallPct)||.60,.1,.9),volPct=clamp(Number(o.volumeComparablePct)||.80,.1,1.5),minMatches=clamp(Math.floor(Number(o.minMatches)||2),1,lookback),horizons=(o.horizons||[1,3,5,10]).map(Number).filter(x=>Number.isInteger(x)&&x>0),events=[];
 for(let i=lookback;i<bars.length;i++){
  const b=bars[i],window=bars.slice(i-lookback,i),r=Math.max(1e-12,b.high-b.low),ranges=window.map(x=>Math.max(0,x.high-x.low)).sort((a,b)=>a-b),medianRange=ranges.length%2?ranges[(ranges.length-1)/2]:(ranges[ranges.length/2-1]+ranges[ranges.length/2])/2;
  const larger=window.filter(x=>(x.high-x.low)>r),matches=larger.filter(x=>Number(x.volume)>0&&Number(b.volume)>=Number(x.volume)*volPct).length,smallRange=medianRange>0&&r<=medianRange*rangePct,body=Math.abs(b.close-b.open),bodyRatio=body/r,divergence=smallRange&&matches>=minMatches&&b.close!==b.open,dir=b.close>b.open?1:-1,forward={};
  if(!divergence)continue;
  for(const h of horizons){const f=bars.slice(i+1,i+h+1);if(f.length<h){forward[h]=null;continue}const end=f[h-1].close;forward[h]={directionalClose:(end-b.close)*dir,favorableExcursion:dir===1?Math.max(...f.map(x=>x.high))-b.close:b.close-Math.min(...f.map(x=>x.low)),adverseExcursion:dir===1?b.close-Math.min(...f.map(x=>x.low)):Math.max(...f.map(x=>x.high))-b.close}}
  events.push({index:i,time:b.time,direction:dir,range:r,medianPriorRange:medianRange,rangeRatio:r/medianRange,body,bodyRatio,volume:Number(b.volume)||0,largerRangeBars:larger.length,comparableVolumeMatches:matches,requiredMatches:minMatches,volumeComparablePct:volPct,forward});
 }
 return {lookback,rangeSmallPct:rangePct,volumeComparablePct:volPct,minMatches,horizons,events,summary:{barsAnalyzed:Math.max(0,bars.length-lookback),candidates:events.length,note:"Comparación individual de volumen contra velas previas de mayor rango; sin promedio de volumen y sin exigir máximo de ventana. Candidatos experimentales, no entradas."}};
}
root.VolumePatternResearch={analyze};
})(typeof window!=="undefined"?window:globalThis);
