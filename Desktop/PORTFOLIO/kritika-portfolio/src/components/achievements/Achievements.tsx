'use client';

import { motion } from 'framer-motion';
import { useInView } from 'react-intersection-observer';

const achievements = [
  {
    icon: '🏆',
    title: 'HackVerse Hackathon Winner 2025',
    description: 'IILM University, Gurugram | PingOn Project',
    colorGradient: 'from-yellow-500/20 to-orange-500/20',
    borderColor: 'yellow-500/50',
    iconColor: 'text-yellow-400',
  },
  {
    icon: '📊',
    title: '99.31% ML Model Accuracy',
    description: 'Brain Tumour Classification System',
    colorGradient: 'from-purple-500/20 to-pink-500/20',
    borderColor: 'purple-500/50',
    iconColor: 'text-purple-400',
  },
  {
    icon: '⚡',
    title: '95% Performance Optimization',
    description: 'Shopify Theme Enhancement at BlackBytt',
    colorGradient: 'from-green-500/20 to-emerald-500/20',
    borderColor: 'green-500/50',
    iconColor: 'text-green-400',
  },
  {
    icon: '📚',
    title: '10+ Technical Documentation Pages',
    description: 'GitBook Documentation for Development Teams',
    colorGradient: 'from-blue-500/20 to-cyan-500/20',
    borderColor: 'blue-500/50',
    iconColor: 'text-blue-400',
  },
  {
    icon: '🎓',
    title: 'Dual Degree Student',
    description: 'IIT Madras (B.S.) + Galgotias (B.Tech.)',
    colorGradient: 'from-indigo-500/20 to-violet-500/20',
    borderColor: 'indigo-500/50',
    iconColor: 'text-indigo-400',
  },
  {
    icon: '🛍️',
    title: '15+ Custom Shopify Sections',
    description: 'Production-Ready E-commerce Components',
    colorGradient: 'from-cyan-500/20 to-teal-500/20',
    borderColor: 'cyan-500/50',
    iconColor: 'text-cyan-400',
  },
];

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1,
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

export default function Achievements() {
  const { ref, inView } = useInView({ threshold: 0.1, triggerOnce: true });

  return (
    <section id="achievements" className="relative py-20 md:py-32 bg-slate-800/50">
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
              <span className="text-slate-300">Achievements & </span>
              <span className="text-cyan-400">Milestones</span>
            </h2>
            <motion.div
              className="w-32 h-1 bg-gradient-to-r from-cyan-500 to-blue-500 mx-auto rounded-full"
              initial={{ width: 0 }}
              animate={inView ? { width: 128 } : {}}
              transition={{ delay: 0.3, duration: 0.8 }}
            />
          </motion.div>

          {/* Achievements Grid - More Spacious */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-10">
            {achievements.map((achievement, index) => {
              const borderColors: Record<string, string> = {
                'yellow-500/50': 'rgba(234, 179, 8, 0.5)',
                'purple-500/50': 'rgba(168, 85, 247, 0.5)',
                'green-500/50': 'rgba(34, 197, 94, 0.5)',
                'blue-500/50': 'rgba(59, 130, 246, 0.5)',
                'indigo-500/50': 'rgba(99, 102, 241, 0.5)',
                'cyan-500/50': 'rgba(6, 182, 212, 0.5)',
              };
              
              return (
                <motion.div
                  key={index}
                  variants={itemVariants}
                  className={`group relative bg-gradient-to-br ${achievement.colorGradient} backdrop-blur-sm rounded-xl p-10 md:p-12 border hover:shadow-2xl transition-all duration-300 overflow-hidden container-content`}
                  style={{
                    borderColor: borderColors[achievement.borderColor] || 'rgba(148, 163, 184, 0.5)',
                    transformOrigin: 'center',
                  }}
                  whileHover={{ scale: 1.03, y: -8 }}
                >
                  <div className={`text-6xl md:text-7xl mb-8 ${achievement.iconColor} transition-transform duration-300`}>
                    {achievement.icon}
                  </div>

                  <h3 className="text-xl md:text-2xl font-bold text-white mb-4">{achievement.title}</h3>
                  <p className="text-slate-400 text-base md:text-lg leading-relaxed">{achievement.description}</p>
                </motion.div>
              );
            })}
          </div>
        </motion.div>
      </div>
    </section>
  );
}
