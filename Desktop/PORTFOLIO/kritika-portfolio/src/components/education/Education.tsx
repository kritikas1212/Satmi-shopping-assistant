'use client';

import { motion } from 'framer-motion';
import { useInView } from 'react-intersection-observer';
import { GraduationCap, Calendar, MapPin } from 'lucide-react';

const education = [
  {
    degree: 'Bachelor of Technology (B.Tech.)',
    major: 'Computer Science and Engineering',
    institution: 'Galgotias College of Engineering and Technology',
    location: 'Greater Noida',
    duration: 'Expected Graduation: 2026',
    icon: '🎓',
  },
  {
    degree: 'Bachelor of Science (B.S.)',
    major: 'Programming and Data Science (Online)',
    institution: 'Indian Institute of Technology (IIT) Madras',
    location: 'Chennai',
    duration: '2022 - 2026',
    icon: '🎓',
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

export default function Education() {
  const { ref, inView } = useInView({ threshold: 0.1, triggerOnce: true });

  return (
    <section id="education" className="relative py-20 md:py-32 bg-slate-900">
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
              <span className="text-slate-300">Education</span>
            </h2>
            <motion.div
              className="w-32 h-1 bg-gradient-to-r from-cyan-500 to-blue-500 mx-auto rounded-full"
              initial={{ width: 0 }}
              animate={inView ? { width: 128 } : {}}
              transition={{ delay: 0.3, duration: 0.8 }}
            />
          </motion.div>

          {/* Education Cards - More Spacious */}
          <div className="grid md:grid-cols-2 gap-12">
            {education.map((edu, index) => (
              <motion.div
                key={index}
                variants={itemVariants}
                className="group relative bg-gradient-to-br from-slate-800/50 to-slate-900/50 backdrop-blur-sm border border-slate-700/50 rounded-xl p-10 md:p-12 hover:border-cyan-500/50 hover:shadow-2xl hover:shadow-cyan-500/10 transition-all duration-300 overflow-hidden container-content"
                whileHover={{ scale: 1.03, y: -8 }}
                style={{ transformOrigin: 'center' }}
              >
                {/* Glow effect */}
                <div className="absolute inset-0 bg-gradient-to-r from-cyan-500/0 via-cyan-500/5 to-cyan-500/0 opacity-0 group-hover:opacity-100 transition-opacity duration-500 rounded-xl" />
                <div className="relative z-10 flex items-start gap-6 mb-8 overflow-hidden">
                  <div className="text-6xl flex-shrink-0">{edu.icon}</div>
                  <div className="flex-1 min-w-0">
                    <h3 className="text-2xl md:text-3xl font-bold text-slate-100 mb-3 group-hover:text-cyan-400 transition-colors break-words">
                      {edu.degree}
                    </h3>
                    <h4 className="text-xl text-cyan-400 mb-2 break-words">{edu.major}</h4>
                  </div>
                </div>

                <div className="relative z-10 space-y-4">
                  <div className="flex items-center gap-3 text-slate-300 text-base">
                    <GraduationCap size={20} className="text-emerald-400" />
                    <span className="font-medium">{edu.institution}</span>
                  </div>
                  <div className="flex items-center gap-3 text-slate-400 text-base">
                    <MapPin size={20} />
                    <span>{edu.location}</span>
                  </div>
                  <div className="flex items-center gap-3 text-slate-400 text-base">
                    <Calendar size={20} />
                    <span>{edu.duration}</span>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </motion.div>
      </div>
    </section>
  );
}
