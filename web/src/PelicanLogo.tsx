import {useEffect, useId, useRef} from 'react';

type Point = {x: number; y: number};

// Each foot follows its pedal; the two leg segments keep a natural bend.
function leg(hip: Point, foot: Point, upper: number, lower: number) {
  const dx = foot.x - hip.x, dy = foot.y - hip.y;
  const distance = Math.hypot(dx, dy);
  const along = (upper * upper - lower * lower + distance * distance) / (2 * distance);
  const height = Math.sqrt(Math.max(0, upper * upper - along * along));
  return `M${hip.x} ${hip.y}L${hip.x + along * dx / distance + height * dy / distance} ${hip.y + along * dy / distance - height * dx / distance}L${foot.x} ${foot.y}`;
}

export default function PelicanLogo() {
  const art = useRef<SVGSVGElement>(null);
  const prefix = useId();

  useEffect(() => {
    const svg = art.current;
    if (!svg) return;
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    let time = .12;
    const names = ['rearSpokes', 'frontSpokes', 'crank', 'nearLeg', 'nearLegColor', 'farLeg', 'nearFoot', 'farFoot', 'body', 'scarfTail', 'shadow'] as const;
    const nodes = Object.fromEntries(names.map(name => [name, svg.querySelector<SVGElement>('[data-part=' + name + ']')!]));
    const transform = (name: string, value: string) => nodes[name].setAttribute('transform', value);
    let frameId = 0, lastFrame: number | null = null, visible = false;
    const draw = () => {
      const angle = time * Math.PI * 2 / 1.6;
      const degrees = angle * 180 / Math.PI, bob = Math.sin(angle * 2) * 1.8;
      transform('rearSpokes', `rotate(${degrees * 29 / 77})`);
      transform('frontSpokes', `rotate(${degrees * 29 / 77})`);
      transform('crank', `translate(554 424) rotate(${degrees})`);
      const foot = {x: 554 + 29 * Math.cos(angle), y: 424 + 29 * Math.sin(angle)};
      const far = {x: 554 - 29 * Math.cos(angle), y: 424 - 29 * Math.sin(angle)};
      const nearPath = leg({x: 535, y: 309 + bob}, foot, 77, 79);
      nodes.nearLeg.setAttribute('d', nearPath);
      nodes.nearLegColor.setAttribute('d', nearPath);
      nodes.farLeg.setAttribute('d', leg({x: 526, y: 310 + bob}, far, 78, 79));
      transform('nearFoot', `translate(${foot.x} ${foot.y - 8})`);
      transform('farFoot', `translate(${far.x} ${far.y - 6})`);
      transform('body', `translate(0 ${bob})`);
      nodes.scarfTail.setAttribute('d', `M580 193Q546 ${182 + Math.sin(angle) * 6} 518 ${197 + Math.sin(angle + 1) * 7}L481 ${187 + Math.sin(angle + 2) * 8}l13 21q45 15 87-6`);
      nodes.shadow.setAttribute('rx', String(222 + bob));
    };
    const frame = (now: number) => {
      if (lastFrame === null) lastFrame = now;
      // Keep DOM updates below 30 fps, without rendering React on every frame.
      if (now - lastFrame >= 1000 / 30) {
        time += Math.min(now - lastFrame, 100) / 1000;
        lastFrame = now;
        draw();
      }
      frameId = requestAnimationFrame(frame);
    };
    const sync = () => {
      if (visible && !document.hidden && !preference.matches) {
        if (!frameId) { lastFrame = null; frameId = requestAnimationFrame(frame); }
      } else {
        cancelAnimationFrame(frameId);
        frameId = 0;
        lastFrame = null;
      }
    };
    const observer = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting && entry.intersectionRect.width > 0 && entry.intersectionRect.height > 0;
      sync();
    });
    observer.observe(svg);
    preference.addEventListener('change', sync);
    document.addEventListener('visibilitychange', sync);
    return () => {
      observer.disconnect();
      preference.removeEventListener('change', sync);
      document.removeEventListener('visibilitychange', sync);
      cancelAnimationFrame(frameId);
    };
  }, []);

  return <svg ref={art} className="pelican-logo" aria-hidden="true" focusable="false" viewBox="0 0 512 512" fill="none">
 <rect x="3" y="3" width="506" height="506" rx="112" fill="#f7f3e8" />
 <circle cx="276" cy="246" r="209" fill="#e3ede1" />
 <defs>
  <g id={prefix + "-wheel"}>
   <circle r="77" fill="#e7e6d1" fillOpacity=".32" stroke="#314c47" strokeWidth="10" />
   <circle r="69" fill="none" stroke="#f6f0d9" strokeWidth="4" />
   <circle r="5" fill="#304d46" />
  </g>
  <g id={prefix + "-spokes"} stroke="#698c82" strokeWidth="1.6" opacity=".7">
   <path d="M-68 0H68M0-68V68M-48-48l96 96M-48 48l96-96M-63-26 63 26M-26-63 26 63M-63 26 63-26M-26 63 26-63" />
  </g>
 </defs>
 <g transform="translate(-300 -45)">
  <ellipse data-part="shadow" cx="551" cy="507" rx="222" ry="14" fill="#667b5a" opacity=".14" />
  <g data-part="rider">
   <path data-part="farLeg" d="M526.000 311.456L587.808 359.035L528.161 410.834" fill="none" stroke="#c8944d" strokeWidth="10" strokeLinecap="round" strokeLinejoin="round" />
   <g data-part="farFoot" transform="translate(528.161 404.834)">
    <path d="M-12-4Q1-7 18 1l5 6h-33Z" fill="#d5a153" stroke="#a7773f" strokeWidth="2" />
   </g>
   <g transform="translate(398 424)">
    <use href={"#" + prefix + "-wheel"} />
    <g data-part="rearSpokes" transform="rotate(10.169)">
     <use href={"#" + prefix + "-spokes"} />
    </g>
    <circle r="6" fill="#476f60" />
   </g>
   <g transform="translate(714 424)">
    <use href={"#" + prefix + "-wheel"} />
    <g data-part="frontSpokes" transform="rotate(10.169)">
     <use href={"#" + prefix + "-spokes"} />
    </g>
    <circle r="6" fill="#476f60" />
   </g>
   <g fill="none" strokeLinecap="round" strokeLinejoin="round">
    <path d="M329 413a70 70 0 0 1 133-25m187-7a77 77 0 0 1 139 29" stroke="#bb794c" strokeWidth="5" />
    <path d="M398 424 475 323 554 424H398l61-84h204L554 424l-79-101m188 17 51 84" stroke="#345d50" strokeWidth="10" />
    <path d="m405 416 69-87m12 17h158" stroke="#83a78b" strokeWidth="2.5" />
    <path d="m475 323-9-30m197 47-20-64q-6-15 10-19l27-2" stroke="#496e5e" strokeWidth="8" />
    <path d="m669 255 19-2" stroke="#ab734d" strokeWidth="10" />
    <path d="M441 295h51" stroke="#354e44" strokeWidth="11" />
    <path d="M438 290q25-8 53 1" stroke="#b57b52" strokeWidth="7" />
    <path d="M397 419 554 405q24 20 0 38L397 430Z" stroke="#647e65" strokeWidth="2" />
   </g>
   <circle cx="554" cy="424" r="21" fill="#628b72" stroke="#365b4c" strokeWidth="3" />
   <circle cx="554" cy="424" r="14" fill="#e1dcc2" stroke="#365b4c" strokeWidth="2" />
   <g data-part="crank" stroke="#334f43" strokeWidth="5" strokeLinecap="round" transform="translate(554 424) rotate(27.000)">
    <path d="M-29 0H29" />
    <circle r="5" fill="#e4ddc3" strokeWidth="2" />
   </g>
   <g data-part="body" transform="translate(0 1.456)">
    <path d="M459 287q-38-5-64-32l13 35-25-5q33 35 79 24" fill="#f9f6e7" stroke="#4b6257" strokeWidth="2.5" strokeLinejoin="round" />
    <path d="M450 245q36-39 89-23l30-54q-3-30 16-43 19-14 40 1 18 17 5 42l-18 60q-5 13-1 29 9 44-31 61-39 20-87 0-49-20-43-73Z" fill="#fcfaed" stroke="#4b6257" strokeWidth="3" />
    <path d="M465 279q45 37 95 17 32-13 35-45-1 48-36 59-63 21-94-31Z" fill="#dce3d0" />
    <path d="M470 253q24-24 57-13 31 12 48 37-32 23-70 12-25-6-35-36Z" fill="#e2e7d6" stroke="#879985" strokeWidth="2" />
    <path d="M482 258q26 13 62 16m-55-5q21 14 43 13" fill="none" stroke="#b0beaa" strokeWidth="2" strokeLinecap="round" />
    <path d="M615 157 754 169q-38 56-90 53-31-4-49-65Z" fill="#edb768" stroke="#946d40" strokeWidth="2.5" strokeLinejoin="round" />
    <path d="M630 173q18 32 40 37 33 1 64-29" fill="none" stroke="#df9a51" strokeWidth="2" />
    <path d="M615 153q53-6 142 14l6 7-145-6Z" fill="#f3cc7b" stroke="#946d40" strokeWidth="2.5" strokeLinejoin="round" />
    <path d="m754 167 9 7-10 3" fill="#dd9251" />
    <circle cx="611" cy="145" r="8" fill="#e8e4bf" />
    <circle cx="612" cy="145" r="4" fill="#2e433a" />
    <circle cx="613" cy="143" r="1.3" fill="white" />
    <path d="M601 131q7-5 13-1" fill="none" stroke="#5d6954" strokeWidth="2" strokeLinecap="round" />
    <path d="M573 127q-2-28 23-32 24-5 32 27" fill="#df8055" stroke="#8e6245" strokeWidth="2.5" />
    <path d="M568 128q34-13 71-2" fill="none" stroke="#aa6041" strokeWidth="7" strokeLinecap="round" />
    <path d="M596 99q-8 10-5 21" fill="none" stroke="#f3ab78" strokeWidth="3" />
    <path data-part="scarfTail" d="M580 193Q542 183 518 201L481 187l13 21q45 15 87-6" fill="#dc7650" stroke="#a75c40" strokeWidth="2" />
    <path d="m568 190 42 10-5 13-43-10Z" fill="#e08459" stroke="#a75c40" strokeWidth="2" />
    <path d="M543 243q21 31 56 38 38 7 73-26" fill="none" stroke="#4b6257" strokeWidth="17" strokeLinecap="round" />
    <path d="M543 242q21 31 56 38 38 7 73-26" fill="none" stroke="#f8f5e6" strokeWidth="12" strokeLinecap="round" />
    <path d="m665 258 11-7" stroke="#e0b15e" strokeWidth="10" strokeLinecap="round" />
   </g>
   <path data-part="nearLeg" d="M535.000 310.456L594.352 359.510L579.839 437.166" fill="none" stroke="#6f6344" strokeWidth="12" strokeLinecap="round" strokeLinejoin="round" />
   <path data-part="nearLegColor" d="M535.000 310.456L594.352 359.510L579.839 437.166" fill="none" stroke="#e4b55f" strokeWidth="8" strokeLinecap="round" strokeLinejoin="round" />
   <g data-part="nearFoot" transform="translate(579.839 429.166)">
    <path d="M-12-4Q1-8 19 0l7 7h-36Z" fill="#efbf66" stroke="#957343" strokeWidth="2" />
    <path d="M-10 11h34" stroke="#344f44" strokeWidth="5" strokeLinecap="round" />
   </g>
  </g>
 </g>
 <path d="M26 241h30m-39 18h26" stroke="#91ac91" strokeWidth="3" strokeLinecap="round" opacity=".6" />
</svg>;
}
