/* XAUUSD Volume Lab — contextual volume/pattern research engine.
 * This module is observational: it does not place trades or change the existing
 * execution rules. It ranks each candle against its own local context, then
 * measures forward price excursions so the hypotheses can be validated on CSV data.
 */
(function (root) {
  "use strict";
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const median = values => {
    const a = values.filter(Number.isFinite).slice().sort((x,y)=>x-y);
    if (!a.length) return 0;
    const m = Math.floor(a.length/2);
    return a.length % 2 ? a[m] : (a[m-1]+a[m])/2;
  };
  const percentileRank = (value, values) => {
    const a = values.filter(Number.isFinite);
    if (!a.length) return 0.5;
    let below=0, equal=0;
    for (const v of a) { if (v < value) below++; else if (v === value) equal++; }
    return (below + equal*0.5) / a.length;
  };
  function analyze(bars, options) {
    const opts = options || {};
    const lookback = clamp(Math.floor(Number(opts.lookback) || 20), 5, 200);
    const horizons = (opts.horizons || [1,3,5,10]).map(Number).filter(n=>Number.isInteger(n)&&n>0);
    const events = [];
    for (let i=lookback; i<bars.length; i++) {
      const b=bars[i], context=bars.slice(i-lookback,i);
      const body=Math.abs(b.close-b.open), range=Math.max(1e-12,b.high-b.low);
      const bodies=context.map(x=>Math.abs(x.close-x.open));
      const volumes=context.map(x=>Number(x.volume)||0);
      const bodyRank=percentileRank(body,bodies);
      const volumeRank=percentileRank(Number(b.volume)||0,volumes);
      const bodyMedian=median(bodies);
      const volumeMedian=median(volumes);
      const relativeBody=bodyMedian>0?body/bodyMedian:null;
      const relativeVolume=volumeMedian>0?(Number(b.volume)||0)/volumeMedian:null;
      const efficiency=body/range;
      // Contextual "effort without result": high local volume rank paired
      // with low local body rank. No absolute volume cutoff is used.
      const effortResultScore=volumeRank-bodyRank;
      const divergenceCandidate=bodyRank<=0.25 && volumeRank>=0.75;
      const direction=b.close>b.open?1:b.close<b.open?-1:0;
      const forward={};
      for (const h of horizons) {
        if (i+h>=bars.length) { forward[h]=null; continue; }
        const future=bars.slice(i+1,i+h+1);
        const end=future[future.length-1].close;
        const favorable=direction===0?null:(end-b.close)*direction;
        const adverse=direction===0?null:-favorable;
        const maxHigh=Math.max(...future.map(x=>x.high));
        const minLow=Math.min(...future.map(x=>x.low));
        forward[h]={closeChange:end-b.close, directionalClose:favorable,
          favorableExcursion:direction===1?maxHigh-b.close:direction===-1?b.close-minLow:null,
          adverseExcursion:direction===1?b.close-minLow:direction===-1?maxHigh-b.close:null};
      }
      if (divergenceCandidate) events.push({
        index:i,time:b.time,direction,body,range,volume:Number(b.volume)||0,
        bodyRank,volumeRank,relativeBody,relativeVolume,efficiency,
        effortResultScore,forward
      });
    }
    return {lookback,horizons,events,summary:{
      barsAnalyzed:Math.max(0,bars.length-lookback),
      candidates:events.length,
      note:"Candidatos contextuales; no son entradas. Los resultados futuros son descriptivos y deben validarse fuera de muestra."
    }};
  }
  root.VolumePatternResearch = { analyze };
})(typeof window !== "undefined" ? window : globalThis);
