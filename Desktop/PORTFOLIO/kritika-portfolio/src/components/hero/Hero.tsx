'use client';

import { useState, useEffect } from 'react';
import { motion, useScroll, useTransform } from 'framer-motion';
import { Github, Linkedin, Mail, Download, ChevronDown, Sparkles, ArrowRight } from 'lucide-react';
import { useInView } from 'react-intersection-observer';

const taglines = [
  'Full-Stack Developer',
  'Shopify Specialist',
  'ML Engineer',
];

// Floating particles component
const FloatingParticle = ({ delay, duration, x, y }: { delay: number; duration: number; x: number; y: number }) => {
  return (
    <motion.div
      className="absolute w-1 h-1 bg-cyan-400/60 rounded-full"
      style={{
        left: `${x}%`,
        top: `${y}%`,
      }}
      animate={{
        y: [0, -100, 0],
        x: [0, Math.sin(delay) * 50, 0],
        opacity: [0, 1, 0],
        scale: [0, 1.5, 0],
      }}
      transition={{
        duration: duration,
        repeat: Infinity,
        ease: 'easeInOut',
        delay: delay,
      }}
    />
  );
};

export default function Hero() {
  const [currentTagline, setCurrentTagline] = useState(0);
  const [displayedText, setDisplayedText] = useState('');
  const [isDeleting, setIsDeleting] = useState(false);
  const [mousePosition, setMousePosition] = useState({ x: 0, y: 0 });
  const { ref, inView } = useInView({ threshold: 0.1, triggerOnce: true });
  const { scrollY } = useScroll();
  const y = useTransform(scrollY, [0, 500], [0, 150]);
  const opacity = useTransform(scrollY, [0, 300], [1, 0]);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      setMousePosition({
        x: (e.clientX / window.innerWidth) * 100,
        y: (e.clientY / window.innerHeight) * 100,
      });
    };

    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, []);

  useEffect(() => {
    const current = taglines[currentTagline];
    let timeout: NodeJS.Timeout;

    if (!isDeleting && displayedText.length < current.length) {
      timeout = setTimeout(() => {
        setDisplayedText(current.substring(0, displayedText.length + 1));
      }, 100);
    } else if (!isDeleting && displayedText.length === current.length) {
      timeout = setTimeout(() => setIsDeleting(true), 2500);
    } else if (isDeleting && displayedText.length > 0) {
      timeout = setTimeout(() => {
        setDisplayedText(current.substring(0, displayedText.length - 1));
      }, 50);
    } else if (isDeleting && displayedText.length === 0) {
      timeout = setTimeout(() => {
        setIsDeleting(false);
        setCurrentTagline((prev) => (prev + 1) % taglines.length);
      }, 200);
    }

    return () => clearTimeout(timeout);
  }, [displayedText, isDeleting, currentTagline]);

  const scrollToSection = (id: string) => {
    const element = document.getElementById(id);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  // Generate particles (using useState to avoid re-renders)
  const particles = useState(() => 
    Array.from({ length: 20 }, (_, i) => ({
      delay: i * 0.2,
      duration: 4 + (i % 3) * 0.5 + 0.5,
      x: (i * 13.7) % 100,
      y: (i * 23.3) % 100,
    }))
  )[0];

  return (
    <section
      id="hero"
      ref={ref}
      className="relative min-h-screen flex items-center justify-center overflow-hidden pt-20"
    >
      {/* Enhanced Animated Background Orbs with Parallax */}
      <div className="absolute inset-0 overflow-hidden">
        <motion.div
          className="absolute top-1/4 left-1/4 w-[500px] h-[500px] bg-blue-500/20 rounded-full blur-3xl"
          style={{ y }}
          animate={{
            x: [0, 100, 0],
            y: [0, 50, 0],
            scale: [1, 1.4, 1],
            opacity: [0.3, 0.5, 0.3],
          }}
          transition={{
            duration: 20,
            repeat: Infinity,
            ease: 'easeInOut',
          }}
        />
        <motion.div
          className="absolute bottom-1/4 right-1/4 w-[500px] h-[500px] bg-emerald-500/20 rounded-full blur-3xl"
          style={{ y }}
          animate={{
            x: [0, -100, 0],
            y: [0, -50, 0],
            scale: [1, 1.4, 1],
            opacity: [0.3, 0.5, 0.3],
          }}
          transition={{
            duration: 25,
            repeat: Infinity,
            ease: 'easeInOut',
          }}
        />
        <motion.div
          className="absolute top-1/2 left-1/2 w-[400px] h-[400px] bg-cyan-500/15 rounded-full blur-3xl transform -translate-x-1/2 -translate-y-1/2"
          animate={{
            x: (mousePosition.x - 50) * 0.1,
            y: (mousePosition.y - 50) * 0.1,
            scale: [1, 1.6, 1],
            opacity: [0.2, 0.4, 0.2],
          }}
          transition={{
            x: { type: 'spring', stiffness: 50, damping: 20 },
            y: { type: 'spring', stiffness: 50, damping: 20 },
            scale: { duration: 15, repeat: Infinity, ease: 'easeInOut' },
            opacity: { duration: 15, repeat: Infinity, ease: 'easeInOut' },
          }}
        />
      </div>

      {/* Floating Particles */}
      {particles.map((particle, i) => (
        <FloatingParticle key={i} {...particle} />
      ))}

      {/* Animated Grid Pattern */}
      <div className="absolute inset-0 opacity-[0.03]">
        <div className="absolute inset-0" style={{
          backgroundImage: `
            linear-gradient(rgba(59, 130, 246, 0.1) 1px, transparent 1px),
            linear-gradient(90deg, rgba(59, 130, 246, 0.1) 1px, transparent 1px)
          `,
          backgroundSize: '50px 50px',
        }} />
      </div>

      {/* Content */}
      <motion.div 
        className="relative z-10 max-w-screen-2xl mx-auto px-6 md:px-8 lg:px-16 xl:px-24 text-center py-20 md:py-32"
        style={{ opacity }}
      >
        <motion.div
          initial={{ opacity: 0, y: 50 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 1, ease: [0.22, 1, 0.36, 1] }}
          className="space-y-12"
        >
          {/* Animated Sparkle Icons */}
          <div className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-20">
            {[...Array(3)].map((_, i) => (
              <motion.div
                key={i}
                className="absolute"
                style={{
                  left: `${-100 + i * 100}px`,
                }}
                animate={{
                  rotate: [0, 360],
                  scale: [0.8, 1.2, 0.8],
                  opacity: [0.3, 1, 0.3],
                }}
                transition={{
                  duration: 3,
                  repeat: Infinity,
                  delay: i * 0.5,
                }}
              >
                <Sparkles className="w-6 h-6 text-cyan-400" />
              </motion.div>
            ))}
          </div>

          {/* Greeting with Stagger Animation - LARGER */}
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={inView ? { opacity: 1, y: 0 } : {}}
            transition={{ delay: 0.2, duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
          >
            <motion.h1
              className="text-6xl md:text-7xl lg:text-8xl font-bold text-slate-100 mb-8 leading-tight"
              initial={{ opacity: 0, scale: 0.9 }}
              animate={inView ? { opacity: 1, scale: 1 } : {}}
              transition={{ delay: 0.3, duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
            >
              <motion.span
                initial={{ opacity: 0, x: -20 }}
                animate={inView ? { opacity: 1, x: 0 } : {}}
                transition={{ delay: 0.4 }}
                className="text-slate-300"
              >
                Hi, I&apos;m{' '}
              </motion.span>
              <motion.span
                className="bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent bg-[length:200%_auto] animate-[gradient_3s_ease_infinite]"
                initial={{ opacity: 0, scale: 0.8 }}
                animate={inView ? { opacity: 1, scale: 1 } : {}}
                transition={{ delay: 0.5, duration: 0.8, type: 'spring', stiffness: 200 }}
              >
                Kritika Singh
              </motion.span>
              <motion.span
                initial={{ opacity: 0, rotate: -20 }}
                animate={inView ? { opacity: 1, rotate: 0 } : {}}
                transition={{ delay: 0.7, type: 'spring', stiffness: 200 }}
                className="inline-block ml-4"
              >
                👋
              </motion.span>
            </motion.h1>
          </motion.div>

          {/* Tagline with typing animation - LARGER */}
          <motion.div
            className="text-3xl md:text-4xl lg:text-5xl font-bold text-slate-400 min-h-[80px] md:min-h-[100px] flex items-center justify-center gap-2 mb-10"
            initial={{ opacity: 0, y: 20 }}
            animate={inView ? { opacity: 1, y: 0 } : {}}
            transition={{ delay: 0.6, duration: 0.8 }}
          >
            <span>I&apos;m a </span>
            <span className="text-cyan-400 font-bold relative">
              {displayedText}
              <motion.span
                className="inline-block ml-1 w-0.5 h-10 bg-cyan-400"
                animate={{ opacity: [1, 0] }}
                transition={{ duration: 0.8, repeat: Infinity }}
              />
            </span>
          </motion.div>

          {/* Description - LARGER with better spacing */}
          <motion.p
            className="text-xl md:text-2xl text-slate-400 max-w-3xl mx-auto leading-relaxed mb-16"
            initial={{ opacity: 0, y: 20 }}
            animate={inView ? { opacity: 1, y: 0 } : {}}
            transition={{ delay: 0.8, duration: 0.8 }}
          >
            Building scalable e-commerce solutions and data-driven applications
          </motion.p>

          {/* Status Badge with Pulse - MORE SPACING */}
          <motion.div
            className="inline-flex items-center space-x-3 px-6 py-3 bg-emerald-500/10 border border-emerald-500/30 rounded-full backdrop-blur-md mb-16"
            initial={{ opacity: 0, scale: 0.8 }}
            animate={inView ? { opacity: 1, scale: 1 } : {}}
            transition={{ delay: 1, duration: 0.8, type: 'spring' }}
            whileHover={{ scale: 1.05 }}
          >
            <motion.span
              className="w-3 h-3 bg-emerald-500 rounded-full"
              animate={{ scale: [1, 1.5, 1], opacity: [1, 0.7, 1] }}
              transition={{ duration: 2, repeat: Infinity }}
            />
            <span className="text-emerald-400 text-base font-medium">
              Available for Opportunities
            </span>
          </motion.div>

          {/* CTAs with Enhanced Animations - MUCH LARGER BUTTONS */}
          <motion.div
            className="flex flex-col sm:flex-row items-center justify-center gap-5 mb-16"
            initial={{ opacity: 0, y: 30 }}
            animate={inView ? { opacity: 1, y: 0 } : {}}
            transition={{ delay: 1.2, duration: 0.8 }}
          >
            <motion.button
              onClick={() => scrollToSection('projects')}
              className="group relative inline-flex items-center gap-4 bg-transparent border-2 border-cyan-500 text-cyan-400 px-12 py-6 rounded-lg text-xl font-semibold transition-all duration-300 hover:bg-cyan-500/10 hover:shadow-lg hover:shadow-cyan-500/50 hover:-translate-y-1 overflow-hidden"
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.98 }}
              initial={{ opacity: 0, x: -20 }}
              animate={inView ? { opacity: 1, x: 0 } : {}}
              transition={{ delay: 1.3 }}
            >
              <span className="relative z-10">View Projects</span>
              <ArrowRight className="w-6 h-6 group-hover:translate-x-1 transition-transform relative z-10" />
              <motion.div
                className="absolute inset-0 bg-cyan-500/5 rounded-lg opacity-0 group-hover:opacity-100"
                initial={false}
              />
            </motion.button>

            <motion.a
              href="/resume.pdf"
              download
              className="group inline-flex items-center gap-4 bg-slate-800/50 border border-slate-700 text-slate-300 px-12 py-6 rounded-lg text-xl font-medium transition-all duration-300 hover:border-slate-600 hover:text-white hover:bg-slate-800 hover:-translate-y-1"
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.98 }}
              initial={{ opacity: 0, x: 20 }}
              animate={inView ? { opacity: 1, x: 0 } : {}}
              transition={{ delay: 1.4 }}
              suppressHydrationWarning
            >
              <Download size={24} className="group-hover:animate-bounce" />
              <span>Download Resume</span>
            </motion.a>
          </motion.div>

          {/* Social Icons with Enhanced Hover - MORE SPACING */}
          <motion.div
            className="flex items-center justify-center gap-6 pt-12"
            initial={{ opacity: 0, y: 20 }}
            animate={inView ? { opacity: 1, y: 0 } : {}}
            transition={{ delay: 1.6, duration: 0.8 }}
          >
            {[
              { icon: Github, href: 'https://github.com/Kritikas1212', label: 'GitHub', color: 'hover:text-slate-100' },
              { icon: Linkedin, href: '#', label: 'LinkedIn', color: 'hover:text-blue-400' },
              { icon: Mail, href: 'mailto:kritikaasinghhh@gmail.com', label: 'Email', color: 'hover:text-emerald-400' },
            ].map(({ icon: Icon, href, label, color }, index) => (
              <motion.a
                key={label}
                href={href}
                target={href.startsWith('http') ? '_blank' : undefined}
                rel={href.startsWith('http') ? 'noopener noreferrer' : undefined}
                className={`group relative p-4 bg-slate-800/50 backdrop-blur-sm border border-slate-700 rounded-xl hover:border-cyan-500 transition-all ${color}`}
                whileHover={{ scale: 1.15, y: -5, rotate: [0, -10, 10, 0] }}
                whileTap={{ scale: 0.9 }}
                title={label}
                suppressHydrationWarning
                initial={{ opacity: 0, scale: 0 }}
                animate={inView ? { opacity: 1, scale: 1 } : {}}
                transition={{ delay: 1.7 + index * 0.1, type: 'spring', stiffness: 200 }}
              >
                <Icon className="w-6 h-6 text-slate-400 group-hover:text-cyan-400 transition-colors" />
                <motion.div
                  className="absolute inset-0 bg-cyan-500/20 rounded-xl opacity-0 group-hover:opacity-100 blur-xl"
                  initial={false}
                />
              </motion.a>
            ))}
          </motion.div>
        </motion.div>
      </motion.div>

      {/* Enhanced Scroll Down Indicator */}
      <motion.div
        className="absolute bottom-12 left-1/2 transform -translate-x-1/2 z-10"
        animate={{ y: [0, 10, 0] }}
        transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
      >
        <button
          onClick={() => scrollToSection('about')}
          className="flex flex-col items-center gap-3 text-slate-400 hover:text-cyan-400 transition-colors group"
          aria-label="Scroll down"
        >
          <span className="text-sm font-medium tracking-wider">SCROLL</span>
          <motion.div
            animate={{ y: [0, 5, 0] }}
            transition={{ duration: 1.5, repeat: Infinity }}
          >
            <ChevronDown size={24} className="group-hover:scale-110 transition-transform" />
          </motion.div>
          <div className="w-px h-8 bg-gradient-to-b from-cyan-400 to-transparent opacity-50" />
        </button>
      </motion.div>
    </section>
  );
}
