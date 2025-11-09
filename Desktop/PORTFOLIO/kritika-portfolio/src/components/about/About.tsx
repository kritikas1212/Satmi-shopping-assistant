'use client';

import { motion } from 'framer-motion';
import { useInView } from 'react-intersection-observer';
import { GraduationCap, Briefcase, Trophy, BarChart3, Zap, ShoppingBag, Sparkles } from 'lucide-react';

const highlights = [
  { icon: GraduationCap, text: 'Dual Degrees: IIT Madras + Galgotias', color: 'text-blue-400', bg: 'from-blue-500/10 to-cyan-500/10' },
  { icon: Briefcase, text: 'Software Developer @ BlackBytt Solutions', color: 'text-emerald-400', bg: 'from-emerald-500/10 to-green-500/10' },
  { icon: Trophy, text: 'HackVerse Hackathon Winner 2025', color: 'text-yellow-400', bg: 'from-yellow-500/10 to-orange-500/10' },
  { icon: BarChart3, text: '99.31% ML Model Accuracy', color: 'text-purple-400', bg: 'from-purple-500/10 to-pink-500/10' },
  { icon: Zap, text: '95% Performance Optimization', color: 'text-orange-400', bg: 'from-orange-500/10 to-red-500/10' },
  { icon: ShoppingBag, text: '15+ Custom Shopify Sections', color: 'text-pink-400', bg: 'from-pink-500/10 to-rose-500/10' },
];

const techStack = {
  Frontend: ['React', 'Next.js', 'TypeScript', 'Tailwind', 'HTML', 'CSS', 'JavaScript'],
  Backend: ['Node.js', 'Python', 'Express'],
  Ecommerce: ['Shopify', 'Liquid', 'JSON Schema'],
  'ML/AI': ['TensorFlow', 'scikit-learn', 'Streamlit'],
  Databases: ['MongoDB', 'MySQL', 'PostgreSQL', 'Bolt'],
  Tools: ['Git', 'GitHub', 'GitBook', 'Canva', 'Google Analytics', 'Adobe Analytics', 'Google Lighthouse'],
};

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1,
      delayChildren: 0.2,
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

export default function About() {
  const { ref, inView } = useInView({ threshold: 0.1, triggerOnce: true });

  return (
    <section id="about" className="relative py-20 md:py-32 bg-slate-900 overflow-hidden">
      {/* Background decoration */}
      <div className="absolute inset-0 opacity-5">
        <div className="absolute top-0 right-0 w-96 h-96 bg-blue-500 rounded-full blur-3xl" />
        <div className="absolute bottom-0 left-0 w-96 h-96 bg-emerald-500 rounded-full blur-3xl" />
      </div>

      <div className="relative z-10 max-w-screen-2xl mx-auto px-6 md:px-8 lg:px-16 xl:px-24">
        <motion.div
          ref={ref}
          initial="hidden"
          animate={inView ? 'visible' : 'hidden'}
          variants={containerVariants}
          className="space-y-16 md:space-y-20"
        >
          {/* Section Header */}
          <motion.div variants={itemVariants} className="text-center">
            <motion.h2
              className="text-5xl md:text-6xl font-bold text-slate-100 mb-16 md:mb-20"
              initial={{ opacity: 0, y: 20 }}
              animate={inView ? { opacity: 1, y: 0 } : {}}
              transition={{ delay: 0.3 }}
            >
              <span className="text-slate-300">About </span>
              <span className="text-cyan-400">Me</span>
            </motion.h2>
            <motion.div
              className="w-32 h-1 bg-gradient-to-r from-cyan-500 to-blue-500 mx-auto rounded-full"
              initial={{ width: 0 }}
              animate={inView ? { width: 128 } : {}}
              transition={{ delay: 0.5, duration: 0.8 }}
            />
          </motion.div>

          {/* Main Content - Two Column Layout */}
          <div className="grid md:grid-cols-2 gap-16 items-center">
            {/* Left Column - Image with Animation */}
            <motion.div
              variants={itemVariants}
              className="flex justify-center md:justify-start"
            >
              <motion.div
                className="relative"
                whileHover={{ scale: 1.05 }}
                transition={{ type: 'spring', stiffness: 300 }}
              >
                {/* Animated gradient border */}
                <motion.div
                  className="absolute inset-0 bg-gradient-to-br from-blue-500 via-cyan-500 to-emerald-500 rounded-2xl blur-xl opacity-50"
                  animate={{
                    rotate: [0, 360],
                    scale: [1, 1.1, 1],
                  }}
                  transition={{
                    rotate: { duration: 20, repeat: Infinity, ease: 'linear' },
                    scale: { duration: 4, repeat: Infinity, ease: 'easeInOut' },
                  }}
                />
                <motion.div
                  className="relative w-64 h-64 md:w-80 md:h-80 bg-gradient-to-br from-slate-800 to-slate-900 rounded-2xl border-2 border-slate-700 flex items-center justify-center overflow-hidden shadow-2xl"
                  initial={{ opacity: 0, scale: 0.8 }}
                  animate={inView ? { opacity: 1, scale: 1 } : {}}
                  transition={{ delay: 0.5, type: 'spring' }}
                >
                  <div className="w-full h-full bg-gradient-to-br from-blue-500/20 via-cyan-500/20 to-emerald-500/20 flex items-center justify-center relative">
                    <motion.span
                      className="text-7xl relative z-10"
                      animate={{
                        y: [0, -10, 0],
                      }}
                      transition={{
                        duration: 3,
                        repeat: Infinity,
                        ease: 'easeInOut',
                      }}
                    >
                      👩‍💻
                    </motion.span>
                    {/* Animated background pattern */}
                    <div className="absolute inset-0 opacity-20">
                      <div className="absolute inset-0" style={{
                        backgroundImage: `radial-gradient(circle at 50% 50%, rgba(255,255,255,0.1) 2px, transparent 2px)`,
                        backgroundSize: '30px 30px',
                      }} />
                    </div>
                  </div>
                </motion.div>
              </motion.div>
            </motion.div>

            {/* Right Column - Content */}
            <motion.div variants={itemVariants} className="space-y-10">
              <motion.p
                className="text-xl md:text-2xl text-slate-300 leading-relaxed"
                initial={{ opacity: 0, x: 20 }}
                animate={inView ? { opacity: 1, x: 0 } : {}}
                transition={{ delay: 0.6 }}
              >
                Results-driven Software Engineer and Full-Stack Developer with hands-on experience in building scalable web applications, optimizing performance, and implementing data-driven solutions. Currently pursuing dual degrees in Computer Science (B.Tech from Galgotias College) and Data Science (B.S. from IIT Madras).
              </motion.p>
              <motion.p
                className="text-xl md:text-2xl text-slate-300 leading-relaxed"
                initial={{ opacity: 0, x: 20 }}
                animate={inView ? { opacity: 1, x: 0 } : {}}
                transition={{ delay: 0.7 }}
              >
                I specialize in modern web technologies including React, Next.js, Node.js, Python, and Shopify development. My work combines technical excellence with business impact, having improved application performance by up to 95% and achieved 99.31% accuracy in machine learning projects.
              </motion.p>
            </motion.div>
          </div>

          {/* Highlights Grid */}
          <motion.div variants={itemVariants}>
            <motion.h3
              className="text-4xl md:text-5xl font-bold text-slate-100 mb-16 text-center"
              initial={{ opacity: 0 }}
              animate={inView ? { opacity: 1 } : {}}
              transition={{ delay: 0.8 }}
            >
              Key Highlights
            </motion.h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-10">
              {highlights.map((highlight, index) => {
                const Icon = highlight.icon;
                return (
                  <motion.div
                    key={index}
                    className={`group relative bg-gradient-to-br ${highlight.bg} backdrop-blur-sm border border-slate-700/50 rounded-xl p-10 md:p-12 overflow-hidden container-content`}
                    initial={{ opacity: 0, y: 30, scale: 0.9 }}
                    animate={inView ? { opacity: 1, y: 0, scale: 1 } : {}}
                    transition={{
                      delay: 0.9 + index * 0.1,
                      type: 'spring',
                      stiffness: 100,
                    }}
                    whileHover={{ 
                      scale: 1.03,
                      y: -8,
                      borderColor: 'rgba(6, 182, 212, 0.5)',
                    }}
                    style={{ transformOrigin: 'center' }}
                  >
                    {/* Animated glow effect */}
                    <motion.div
                      className="absolute inset-0 bg-gradient-to-r from-cyan-500/0 via-cyan-500/20 to-cyan-500/0 opacity-0 group-hover:opacity-100"
                      animate={{
                        x: ['-100%', '100%'],
                      }}
                      transition={{
                        duration: 1.5,
                        repeat: Infinity,
                        ease: 'linear',
                      }}
                    />
                    <div className="relative z-10 h-full flex flex-col overflow-hidden">
                      <Icon className={`w-14 h-14 mb-6 ${highlight.color} flex-shrink-0`} />
                      <p className="text-slate-300 font-medium text-lg leading-relaxed break-words">{highlight.text}</p>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          </motion.div>

          {/* Tech Stack */}
          <motion.div variants={itemVariants} className="space-y-8">
            <motion.h3
              className="text-4xl md:text-5xl font-bold text-slate-100 mb-16 text-center"
              initial={{ opacity: 0 }}
              animate={inView ? { opacity: 1 } : {}}
              transition={{ delay: 1.5 }}
            >
              Tech Stack
            </motion.h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-12">
              {Object.entries(techStack).map(([category, technologies], categoryIndex) => (
              <motion.div
                key={category}
                className="group relative bg-gradient-to-br from-slate-800/50 to-slate-900/50 backdrop-blur-sm border border-slate-700/50 rounded-xl p-10 md:p-12 overflow-hidden container-content"
                initial={{ opacity: 0, y: 30 }}
                animate={inView ? { opacity: 1, y: 0 } : {}}
                transition={{
                  delay: 1.6 + categoryIndex * 0.1,
                  type: 'spring',
                }}
                whileHover={{ 
                  scale: 1.03,
                  y: -8,
                  borderColor: 'rgba(6, 182, 212, 0.5)',
                }}
                style={{ transformOrigin: 'center' }}
              >
                {/* Glow effect */}
                <motion.div
                  className="absolute inset-0 bg-gradient-to-r from-cyan-500/0 via-cyan-500/10 to-cyan-500/0 opacity-0 group-hover:opacity-100"
                  animate={{
                    x: ['-100%', '100%'],
                  }}
                  transition={{
                    duration: 2,
                    repeat: Infinity,
                    ease: 'linear',
                  }}
                />
                <div className="relative z-10 h-full flex flex-col">
                  <h4 className="text-xl md:text-2xl font-semibold text-cyan-400 mb-8">{category}</h4>
                  <div className="flex flex-wrap gap-4">
                    {technologies.map((tech, techIndex) => (
                      <motion.span
                        key={tech}
                        className="px-5 py-2.5 bg-slate-700/50 text-slate-300 rounded-lg text-base border border-slate-600 hover:border-cyan-500/50 hover:text-cyan-400 transition-all cursor-default backdrop-blur-sm"
                        whileHover={{ scale: 1.05 }}
                        initial={{ opacity: 0, scale: 0.8 }}
                        animate={inView ? { opacity: 1, scale: 1 } : {}}
                        transition={{
                          delay: 1.7 + (categoryIndex * 0.1) + (techIndex * 0.03),
                          type: 'spring',
                        }}
                      >
                        {tech}
                      </motion.span>
                    ))}
                  </div>
                </div>
              </motion.div>
              ))}
            </div>
          </motion.div>
        </motion.div>
      </div>
    </section>
  );
}
