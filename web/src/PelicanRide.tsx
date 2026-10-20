import {useEffect, useRef, useState} from 'react';
import {Bell, FastForward, Pause, Play} from 'lucide-react';
import './pelican-ride.css';

type Point = {x: number; y: number};

// Each foot follows its pedal; the two leg segments keep a natural bend.
function leg(hip: Point, foot: Point, upper: number, lower: number) {
  const dx = foot.x - hip.x, dy = foot.y - hip.y;
  const distance = Math.hypot(dx, dy);
  const along = (upper * upper - lower * lower + distance * distance) / (2 * distance);
  const height = Math.sqrt(Math.max(0, upper * upper - along * along));
  return `M${hip.x} ${hip.y}L${hip.x + along * dx / distance + height * dy / distance} ${hip.y + along * dy / distance - height * dx / distance}L${foot.x} ${foot.y}`;
}

export default function PelicanRide() {
  const [playing, setPlaying] = useState(() => !window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const [fast, setFast] = useState(false);
  const [ringing, setRinging] = useState(false);
  const [soundUnavailable, setSoundUnavailable] = useState(false);
  const art = useRef<SVGSVGElement>(null);
  const time = useRef(.12);
  const speed = useRef(1);
  const audio = useRef<AudioContext | null>(null);
  const bellTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastRing = useRef(-Infinity);
  const mounted = useRef(false);
  speed.current = fast ? 2.2 : 1;

  useEffect(() => {
    mounted.current = true;
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    const reduceMotion = () => { if (preference.matches) setPlaying(false); };
    const quietWhenHidden = () => { if (document.hidden) void audio.current?.suspend().catch(() => {}); };
    preference.addEventListener('change', reduceMotion);
    document.addEventListener('visibilitychange', quietWhenHidden);
    return () => {
      mounted.current = false;
      preference.removeEventListener('change', reduceMotion);
      document.removeEventListener('visibilitychange', quietWhenHidden);
      if (bellTimer.current !== null) clearTimeout(bellTimer.current);
      if (audio.current) void audio.current.close().catch(() => {});
      audio.current = null;
    };
  }, []);

  useEffect(() => {
    const svg = art.current;
    if (!svg || !playing) return;
    const names = ['rearSpokes', 'frontSpokes', 'crank', 'nearLeg', 'nearLegColor', 'farLeg', 'nearFoot', 'farFoot', 'body', 'scarfTail', 'road', 'shadow'] as const;
    const nodes = Object.fromEntries(names.map(name => [name, svg.querySelector<SVGElement>('#sidebar-ride-' + name)!]));
    const transform = (name: string, value: string) => nodes[name].setAttribute('transform', value);
    let frameId = 0, lastFrame: number | null = null, visible = false;
    const draw = () => {
      const angle = time.current * Math.PI * 2 / 1.6;
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
      transform('road', `translate(${-angle * 29 % 90} 0)`);
      nodes.shadow.setAttribute('rx', String(222 + bob));
    };
    const frame = (now: number) => {
      if (lastFrame === null) lastFrame = now;
      // Keep DOM updates below 30 fps, without rendering React on every frame.
      if (now - lastFrame >= 1000 / 30) {
        time.current += Math.min(now - lastFrame, 100) / 1000 * speed.current;
        lastFrame = now;
        draw();
      }
      frameId = requestAnimationFrame(frame);
    };
    const sync = () => {
      if (visible && !document.hidden) {
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
    document.addEventListener('visibilitychange', sync);
    return () => {
      observer.disconnect();
      document.removeEventListener('visibilitychange', sync);
      cancelAnimationFrame(frameId);
    };
  }, [playing]);

  const ringBell = async () => {
    // Bound repeated taps, both to keep the bell gentle and to limit audio nodes.
    const now = performance.now();
    if (now - lastRing.current < 900) return;
    lastRing.current = now;
    setRinging(true);
    setSoundUnavailable(false);
    if (bellTimer.current !== null) clearTimeout(bellTimer.current);
    bellTimer.current = setTimeout(() => {
      setRinging(false);
      void audio.current?.suspend().catch(() => {});
    }, 900);
    try {
      const Audio = window.AudioContext || (window as typeof window & {webkitAudioContext?: typeof AudioContext}).webkitAudioContext;
      if (!Audio) throw new Error('Web Audio is unavailable');
      const context = audio.current || new Audio();
      audio.current = context;
      if (context.state !== 'running') await context.resume();
      if (!mounted.current || document.hidden || context.state !== 'running' || lastRing.current !== now || performance.now() - now > 900) return;
      // A small, local two-strike bicycle bell. No downloaded audio or API call.
      const start = context.currentTime + .015;
      for (const offset of [0, .15]) {
        for (const [frequency, volume, decay] of [[1760, .075, .38], [3520, .025, .25], [4840, .01, .17]]) {
          const oscillator = context.createOscillator();
          const gain = context.createGain();
          oscillator.frequency.value = frequency;
          gain.gain.setValueAtTime(0, start + offset);
          gain.gain.linearRampToValueAtTime(volume, start + offset + .004);
          gain.gain.exponentialRampToValueAtTime(.0001, start + offset + decay);
          oscillator.connect(gain);
          gain.connect(context.destination);
          oscillator.onended = () => { oscillator.disconnect(); gain.disconnect(); };
          oscillator.start(start + offset);
          oscillator.stop(start + offset + decay + .02);
        }
      }
    } catch {
      if (mounted.current) setSoundUnavailable(true);
    }
  };

  return <section className="sidebar-ride" aria-label="和鹈鹕先生一起骑行" data-fast={fast} data-ringing={ringing}>
    <button type="button" className="pelican-ride-scene" aria-label={playing ? '暂停鹈鹕骑行动画' : '播放鹈鹕骑行动画'} title={playing ? '点击暂停骑行' : '点击继续骑行'} onClick={() => setPlaying(value => !value)}>
<svg ref={art} viewBox="285 65 540 460" fill="none" aria-hidden="true" focusable="false" className="pelican-ride-art">
<defs>
  <clipPath id="sidebar-ride-road-clip"><path d="M320 514h470v10H320z"/></clipPath>
  <g id="sidebar-ride-wheel">
   <circle r="77" fill="#e7e6d1" fillOpacity=".32" stroke="#314c47" strokeWidth="10" />
   <circle r="69" fill="none" stroke="#f6f0d9" strokeWidth="4" />
   <circle r="5" fill="#304d46" />
  </g>
  <g id="sidebar-ride-spokes" stroke="#698c82" strokeWidth="1.6" opacity=".7">
   <path d="M-68 0H68M0-68V68M-48-48l96 96M-48 48l96-96M-63-26 63 26M-26-63 26 63M-63 26 63-26M-26 63 26-63" />
  </g>
 </defs>
<path d="M320 511H790" stroke="#dce2ed" strokeWidth="2" strokeLinecap="round"/>
<g clipPath="url(#sidebar-ride-road-clip)"><g id="sidebar-ride-road" stroke="#929ac4" strokeWidth="2.5" strokeLinecap="round" opacity=".55"><path d="M247 520h36m54 0h36m54 0h36m54 0h36m54 0h36m54 0h36m54 0h36m54 0h36m54 0h36"/></g></g>

  <ellipse id="sidebar-ride-shadow" cx="551" cy="507" rx="222" ry="14" fill="#667b5a" opacity=".14" />
  <g id="sidebar-ride-rider">
   <path id="sidebar-ride-farLeg" d="M526.000 311.456L587.808 359.035L528.161 410.834" fill="none" stroke="#c8944d" strokeWidth="10" strokeLinecap="round" strokeLinejoin="round" />
   <g id="sidebar-ride-farFoot" transform="translate(528.161 404.834)">
    <path d="M-12-4Q1-7 18 1l5 6h-33Z" fill="#d5a153" stroke="#a7773f" strokeWidth="2" />
   </g>
   <g transform="translate(398 424)">
    <use href="#sidebar-ride-wheel" />
    <g id="sidebar-ride-rearSpokes" transform="rotate(10.169)">
     <use href="#sidebar-ride-spokes" />
    </g>
    <circle r="6" fill="#476f60" />
   </g>
   <g transform="translate(714 424)">
    <use href="#sidebar-ride-wheel" />
    <g id="sidebar-ride-frontSpokes" transform="rotate(10.169)">
     <use href="#sidebar-ride-spokes" />
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
   <g id="sidebar-ride-crank" stroke="#334f43" strokeWidth="5" strokeLinecap="round" transform="translate(554 424) rotate(27.000)">
    <path d="M-29 0H29" />
    <circle r="5" fill="#e4ddc3" strokeWidth="2" />
   </g>
   <g id="sidebar-ride-body" transform="translate(0 1.456)">
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
    <path id="sidebar-ride-scarfTail" d="M580 193Q542 183 518 201L481 187l13 21q45 15 87-6" fill="#dc7650" stroke="#a75c40" strokeWidth="2" />
    <path d="m568 190 42 10-5 13-43-10Z" fill="#e08459" stroke="#a75c40" strokeWidth="2" />
    <path d="M543 243q21 31 56 38 38 7 73-26" fill="none" stroke="#4b6257" strokeWidth="17" strokeLinecap="round" />
    <path d="M543 242q21 31 56 38 38 7 73-26" fill="none" stroke="#f8f5e6" strokeWidth="12" strokeLinecap="round" />
    <path d="m665 258 11-7" stroke="#e0b15e" strokeWidth="10" strokeLinecap="round" />
   </g>
   <path id="sidebar-ride-nearLeg" d="M535.000 310.456L594.352 359.510L579.839 437.166" fill="none" stroke="#6f6344" strokeWidth="12" strokeLinecap="round" strokeLinejoin="round" />
   <path id="sidebar-ride-nearLegColor" d="M535.000 310.456L594.352 359.510L579.839 437.166" fill="none" stroke="#e4b55f" strokeWidth="8" strokeLinecap="round" strokeLinejoin="round" />
   <g id="sidebar-ride-nearFoot" transform="translate(579.839 429.166)">
    <path d="M-12-4Q1-8 19 0l7 7h-36Z" fill="#efbf66" stroke="#957343" strokeWidth="2" />
    <path d="M-10 11h34" stroke="#344f44" strokeWidth="5" strokeLinecap="round" />
   </g>
  </g></svg>
      <span className="pelican-ride-play" aria-hidden="true">{playing ? <Pause size={11}/> : <Play size={11}/>}</span>
      <span className="pelican-ride-ding" aria-hidden="true">叮铃<span>♪</span></span>
    </button>
    <div className="pelican-ride-controls">
      <button type="button" aria-label="加速骑行" aria-pressed={fast} title={fast ? '已加速，再点恢复正常速度' : '加速骑行'} onClick={() => setFast(value => !value)}><FastForward size={13}/><span>加速</span></button>
      <button type="button" aria-label="按铃" title="按响车铃" onClick={() => void ringBell()}><Bell size={13}/><span>按铃</span></button>
    </div>
    <p className="pelican-ride-caption"><span>和鹈鹕先生一起，</span><strong>把想法变成<br/><em>看得见的视频</em></strong></p>
    <span className="sr-only" role="status">{ringing ? (soundUnavailable ? '叮铃！当前浏览器未能播放铃声。' : '叮铃！') : ''}</span>
  </section>;
}
