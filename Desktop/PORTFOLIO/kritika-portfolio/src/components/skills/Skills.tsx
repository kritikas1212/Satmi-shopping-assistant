'use client';

import { motion } from 'framer-motion';
import { useInView } from 'react-intersection-observer';

const skillCategories = [
  {
    category: 'Programming & Analytics',
    icon: '💻',
    skills: [
      { name: 'Python', level: 85 },
      { name: 'JavaScript', level: 85 },
      { name: 'TypeScript', level: 75 },
      { name: 'SQL', level: 70 },
      { name: 'C/C++', level: 65 },
      { name: 'Java', level: 60 },
      { name: 'Shopify Liquid', level: 80 },
      { name: 'HTML/CSS', level: 90 },
    ],
  },
  {
    category: 'Frameworks & Libraries',
    icon: '⚛️',
    skills: [
      { name: 'React', level: 85 },
      { name: 'Next.js', level: 80 },
      { name: 'Node.js', level: 80 },
      { name: 'Tailwind CSS', level: 85 },
      { name: 'React Native', level: 70 },
    ],
  },
  {
    category: 'E-commerce & Analytics',
    icon: '🛍️',
    skills: [
      { name: 'Shopify Development', level: 85 },
      { name: 'Google Analytics', level: 80 },
      { name: 'Adobe Analytics', level: 70 },
      { name: 'Google Lighthouse', level: 90 },
    ],
  },
  {
    category: 'Databases',
    icon: '🗄️',
    skills: [
      { name: 'MongoDB', level: 75 },
      { name: 'MySQL', level: 80 },
      { name: 'PostgreSQL', level: 70 },
      { name: 'SQL', level: 80 },
    ],
  },
  {
    category: 'Tools & Platforms',
    icon: '🛠️',
    skills: [
      { name: 'Git/GitHub', level: 90 },
      { name: 'GitBook', level: 85 },
      { name: 'Canva', level: 80 },
      { name: 'VS Code', level: 95 },
      { name: 'Vercel/Netlify', level: 85 },
    ],
  },
  {
    category: 'Machine Learning',
    icon: '🤖',
    skills: [
      { name: 'TensorFlow', level: 75 },
      { name: 'scikit-learn', level: 80 },
      { name: 'Computer Vision', level: 70 },
      { name: 'Transfer Learning', level: 80 },
    ],
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

export default function Skills() {
  const { ref, inView } = useInView({ threshold: 0.1, triggerOnce: true });

  return (
    <section id="skills" className="relative py-20 md:py-32 bg-slate-900">
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
              <span className="text-slate-300">Skills & </span>
              <span className="text-cyan-400">Expertise</span>
            </h2>
            <motion.div
              className="w-32 h-1 bg-gradient-to-r from-cyan-500 to-blue-500 mx-auto rounded-full"
              initial={{ width: 0 }}
              animate={inView ? { width: 128 } : {}}
              transition={{ delay: 0.3, duration: 0.8 }}
            />
          </motion.div>

          {/* Skills Grid - Brittany Chiang Style */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-12 md:gap-16">
            {skillCategories.map((category, categoryIndex) => (
              <motion.div
                key={category.category}
                variants={itemVariants}
                className="group"
              >
                {/* Category Title - More spacing */}
                <h3 className="text-xl font-bold text-cyan-400 mb-8 flex items-center gap-3">
                  <span className="text-2xl">{category.icon}</span>
                  {category.category}
                </h3>

                {/* Skills List - More spacing */}
                <div className="space-y-6">
                  {category.skills.map((skill, skillIndex) => (
                    <div key={skill.name} className="group/skill">
                      {/* Skill name and percentage */}
                      <div className="flex justify-between items-baseline mb-3">
                        <span className="text-slate-300 text-base font-medium group-hover/skill:text-cyan-400 transition-colors">
                          {skill.name}
                        </span>
                        <span className="text-cyan-400 font-bold text-sm">
                          {skill.level}%
                        </span>
                      </div>

                      {/* Progress bar - Taller */}
                      <div className="h-2.5 bg-slate-800 rounded-full overflow-hidden border border-slate-700/50">
                        <motion.div
                          className="h-full bg-gradient-to-r from-cyan-500 to-blue-500 rounded-full transition-all duration-1000 ease-out relative overflow-hidden"
                          style={{ width: `${skill.level}%` }}
                          initial={{ width: 0 }}
                          animate={inView ? { width: `${skill.level}%` } : { width: 0 }}
                          transition={{
                            delay: (categoryIndex * 0.1) + (skillIndex * 0.05),
                            duration: 1,
                            ease: 'easeOut',
                          }}
                        >
                          {/* Shine effect */}
                          <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/30 to-transparent -translate-x-full group-hover/skill:translate-x-full transition-transform duration-1000" />
                        </motion.div>
                      </div>
                    </div>
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
