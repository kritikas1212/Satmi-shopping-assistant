'use client';

import { motion } from 'framer-motion';
import { useInView } from 'react-intersection-observer';
import { Calendar, MapPin } from 'lucide-react';

const experiences = [
  {
    company: 'BlackBytt Software Solutions',
    role: 'Software Developer Intern',
    duration: 'September 2025 - Present',
    location: 'Remote',
    achievements: [
      'Developed and deployed 15+ custom Shopify theme sections using HTML, CSS, JavaScript, and JSON schema',
      'Enhanced theme performance by 95% (Google Lighthouse) and reduced page load time by ~40%',
      'Optimized workflow efficiency by 30% via Git and GitHub',
      'Authored 10+ detailed GitBook documentation pages, improving onboarding by ~50%',
      'Collaborated with UI/UX designers and backend engineers for modular components',
      'Delivered scalable, accessible, SEO-optimized Shopify themes',
    ],
    tech: ['Shopify', 'Liquid', 'JavaScript', 'HTML', 'CSS', 'Git', 'GitBook'],
  },
  {
    company: 'EazyBytes Web Solutions',
    role: 'Summer Internship',
    duration: 'June 2025 - July 2025',
    location: 'Remote',
    achievements: [
      'Developed responsive web applications using HTML, CSS, JavaScript',
      'Implemented UI components and optimized website performance',
      'Gained hands-on experience with Git, API integration, Agile development',
    ],
    tech: ['HTML', 'CSS', 'JavaScript', 'Git', 'REST APIs'],
  },
];

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.2,
    },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 30 },
  visible: {
    opacity: 1,
    y: 0,
  },
};

export default function Experience() {
  const { ref, inView } = useInView({ threshold: 0.1, triggerOnce: true });

  return (
    <section id="experience" className="relative py-20 md:py-32 bg-slate-800/50">
      <div className="max-w-screen-2xl mx-auto px-6 md:px-8 lg:px-16 xl:px-24">
        <motion.div
          ref={ref}
          initial="hidden"
          animate={inView ? 'visible' : 'hidden'}
          variants={containerVariants}
          className="space-y-16 md:space-y-20"
        >
          {/* Section Header */}
          <motion.div variants={itemVariants} className="text-center">
            <h2 className="text-5xl md:text-6xl font-bold text-slate-100 mb-16 md:mb-20">
              <span className="text-slate-300">Work </span>
              <span className="text-cyan-400">Experience</span>
            </h2>
            <motion.div
              className="w-32 h-1 bg-gradient-to-r from-cyan-500 to-blue-500 mx-auto rounded-full"
              initial={{ width: 0 }}
              animate={inView ? { width: 128 } : {}}
              transition={{ delay: 0.3, duration: 0.8 }}
            />
          </motion.div>

          {/* Experience Items - Brittany Chiang Style (No Timeline) */}
          <div className="space-y-16 md:space-y-20">
            {experiences.map((exp, index) => (
              <motion.div
                key={index}
                variants={itemVariants}
                className="group relative"
              >
                {/* Company & Role Header - More spacing */}
                <div className="flex flex-wrap items-baseline justify-between gap-4 mb-6">
                  <div>
                    <h3 className="text-2xl md:text-3xl font-bold text-white mb-2 group-hover:text-cyan-400 transition-colors">
                      {exp.role}
                    </h3>
                    <div className="text-xl text-cyan-400 font-semibold">
                      {exp.company}
                    </div>
                  </div>
                  <div className="text-slate-500 font-mono text-sm uppercase tracking-wider">
                    {exp.duration}
                  </div>
                </div>

                {/* Meta info - More spacing */}
                <div className="flex flex-wrap gap-6 text-slate-400 text-base mb-8">
                  <span className="flex items-center gap-2">
                    <MapPin size={18} />
                    {exp.location}
                  </span>
                </div>

                {/* Achievements - More spacing between items */}
                <ul className="space-y-5 text-slate-300 text-lg md:text-xl leading-relaxed mb-10">
                  {exp.achievements.map((achievement, i) => (
                    <motion.li
                      key={i}
                      className="flex gap-5"
                      initial={{ opacity: 0, x: -20 }}
                      animate={inView ? { opacity: 1, x: 0 } : {}}
                      transition={{ delay: index * 0.2 + i * 0.1 }}
                    >
                      <span className="text-cyan-400 text-xl mt-1 flex-shrink-0">▹</span>
                      <span className="break-words">{achievement}</span>
                    </motion.li>
                  ))}
                </ul>

                {/* Tech Tags - Larger with more spacing */}
                <div className="flex flex-wrap gap-4">
                  {exp.tech.map((tech) => (
                    <motion.span
                      key={tech}
                      className="bg-cyan-500/10 text-cyan-300 px-5 py-2.5 rounded-lg text-base font-medium border border-cyan-500/20 overflow-hidden"
                      whileHover={{ scale: 1.05, borderColor: 'rgba(6, 182, 212, 0.5)' }}
                      initial={{ opacity: 0, scale: 0.8 }}
                      animate={inView ? { opacity: 1, scale: 1 } : {}}
                      transition={{ delay: index * 0.2 + exp.tech.indexOf(tech) * 0.05 }}
                      style={{ transformOrigin: 'center' }}
                    >
                      {tech}
                    </motion.span>
                  ))}
                </div>
              </motion.div>
            ))}
          </div>
        </motion.div>
      </div>
    </section>
  );
}
