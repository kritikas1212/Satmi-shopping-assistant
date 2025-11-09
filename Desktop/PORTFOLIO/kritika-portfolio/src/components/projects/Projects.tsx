'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useInView } from 'react-intersection-observer';
import { ExternalLink, Github, ChevronDown, ChevronUp, Trophy, Sparkles } from 'lucide-react';

const projects = [
  {
    id: 1,
    title: 'Brain Tumour Classification Using Deep Learning',
    date: 'July 2025 - November 2025',
    description: 'Deep learning system achieving 99.31% accuracy in brain tumour classification',
    thumbnail: '🧠',
    gradient: 'from-purple-500/20 via-pink-500/20 to-rose-500/20',
    metrics: [
      { label: '99.31% Accuracy', value: '99.31', suffix: '%' },
      { label: '8,334+ MRI Scans', value: '8.3K', suffix: '+' },
      { label: '99.29% Precision', value: '99.29', suffix: '%' },
      { label: '<1 Second Inference', value: '<1', suffix: 's' },
    ],
    tech: ['Python', 'TensorFlow', 'Streamlit', 'ResNet50', 'EfficientNet-B3'],
    features: [
      'Developed deep learning system achieving 99.31% accuracy across 4 tumour categories',
      'Implemented transfer learning optimization reducing training time by 20x (12-16 epochs)',
      'Built production web application on Streamlit Cloud with interactive heatmap visualization',
      'Dual-model support: ResNet50 (98.77%) and EfficientNet-B3 (99.31%)',
      'Enhanced model robustness through advanced data augmentation',
      '85% validation loss reduction and perfect classification on healthy brain scans',
    ],
    links: {
      live: 'https://deeplearningbraintumourdetection.streamlit.app/',
      github: '#',
    },
  },
  {
    id: 2,
    title: 'PingOn - SaaS Uptime Monitoring',
    date: 'April 2025',
    badge: '🏆 HackVerse Hackathon 2025 Winner',
    description: 'Full-stack uptime monitoring platform for tracking website and API availability',
    thumbnail: '📊',
    gradient: 'from-blue-500/20 via-cyan-500/20 to-teal-500/20',
    metrics: [
      { label: 'Real-time Analytics', value: '100', suffix: '%' },
      { label: 'Instant Alerts', value: '100', suffix: '%' },
      { label: 'Performance Insights', value: '100', suffix: '%' },
      { label: 'Anomaly Detection', value: '100', suffix: '%' },
    ],
    tech: ['TypeScript', 'React', 'Tailwind CSS', 'Vite', 'BoltDB', 'Data Mining'],
    features: [
      'Developed SaaS uptime monitoring web app to track website/API availability',
      'Built responsive full-stack platform with real-time analytics and alerts',
      'Applied data mining techniques to process uptime logs and detect anomalies',
      'Generate comprehensive performance insights',
    ],
    links: {
      live: 'https://pingon.netlify.app/',
      github: '#',
    },
  },
  {
    id: 3,
    title: 'Shopify Performance Optimizer',
    date: 'September 2025 - Present',
    description: 'Custom Shopify theme optimization achieving 95% performance improvement',
    thumbnail: '⚡',
    gradient: 'from-emerald-500/20 via-green-500/20 to-lime-500/20',
    metrics: [
      { label: '95% Performance', value: '95', suffix: '%' },
      { label: '40% Faster Load', value: '40', suffix: '%' },
      { label: '15+ Custom Sections', value: '15', suffix: '+' },
      { label: '100% Responsive', value: '100', suffix: '%' },
    ],
    tech: ['Shopify Liquid', 'JavaScript', 'CSS', 'JSON Schema'],
    features: [
      'Strategic lazy loading and asset compression',
      'Code minification and optimization',
      'SEO-optimized theme development',
      'Modular, reusable component library',
    ],
    links: {
      live: '#',
      github: '#',
    },
  },
];

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.15,
    },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 50, scale: 0.9 },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
  },
};

export default function Projects() {
  const { ref, inView } = useInView({ threshold: 0.1, triggerOnce: true });
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [hoveredId, setHoveredId] = useState<number | null>(null);

  return (
    <section id="projects" className="relative py-20 md:py-32 bg-slate-800/50 overflow-hidden">
      {/* Background decoration */}
      <div className="absolute inset-0 opacity-10">
        <div className="absolute top-0 left-0 w-96 h-96 bg-cyan-500 rounded-full blur-3xl" />
        <div className="absolute bottom-0 right-0 w-96 h-96 bg-blue-500 rounded-full blur-3xl" />
      </div>

      <div className="relative z-10 max-w-screen-2xl mx-auto px-6 md:px-8 lg:px-16 xl:px-24">
        <motion.div
          ref={ref}
          initial="hidden"
          animate={inView ? 'visible' : 'hidden'}
          variants={containerVariants}
          className="space-y-16 md:space-y-20"
        >
          {/* Section Header with Animation */}
          <motion.div
            variants={itemVariants}
            className="text-center"
          >
            <motion.h2
              className="text-5xl md:text-6xl font-bold text-slate-100 mb-16 md:mb-20"
              initial={{ opacity: 0, y: 20 }}
              animate={inView ? { opacity: 1, y: 0 } : {}}
              transition={{ delay: 0.3 }}
            >
              <span className="text-slate-300">Featured </span>
              <span className="text-cyan-400">Projects</span>
            </motion.h2>
            <motion.div
              className="w-32 h-1 bg-gradient-to-r from-cyan-500 to-blue-500 mx-auto rounded-full"
              initial={{ width: 0 }}
              animate={inView ? { width: 128 } : {}}
              transition={{ delay: 0.5, duration: 0.8 }}
            />
          </motion.div>

          {/* Projects Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-12">
            {projects.map((project, index) => (
              <motion.div
                key={project.id}
                variants={itemVariants}
                className="group relative"
                onHoverStart={() => setHoveredId(project.id)}
                onHoverEnd={() => setHoveredId(null)}
              >
                <motion.div
                  className="group relative bg-slate-900/50 rounded-2xl p-8 md:p-10 border border-slate-800 hover:border-slate-700 transition-all duration-500 hover:-translate-y-2 hover:shadow-2xl hover:shadow-cyan-500/5 h-full flex flex-col overflow-hidden container-content"
                  whileHover={{ 
                    y: -8,
                    scale: 1.03,
                    borderColor: 'rgba(6, 182, 212, 0.5)',
                  }}
                  transition={{ type: 'spring', stiffness: 300, damping: 20 }}
                  style={{ transformOrigin: 'center' }}
                >
                  {/* Image/Icon Section - BIGGER */}
                  <div className={`relative h-56 md:h-64 bg-gradient-to-br ${project.gradient} rounded-xl mb-8 flex items-center justify-center overflow-hidden`}>
                    <motion.div
                      className="text-8xl"
                      animate={{
                        scale: hoveredId === project.id ? [1, 1.2, 1] : 1,
                        rotate: hoveredId === project.id ? [0, 5, -5, 0] : 0,
                      }}
                      transition={{ duration: 0.5 }}
                    >
                      {project.thumbnail}
                    </motion.div>

                    {/* Animated Background Pattern */}
                    <div className="absolute inset-0 opacity-20">
                      <div className="absolute inset-0" style={{
                        backgroundImage: `radial-gradient(circle at 50% 50%, rgba(255,255,255,0.1) 1px, transparent 1px)`,
                        backgroundSize: '20px 20px',
                      }} />
                    </div>

                    {/* Hover Overlay with Buttons */}
                    <div className="absolute inset-0 bg-slate-950/95 opacity-0 group-hover:opacity-100 transition-all duration-300 flex flex-col items-center justify-center gap-5 p-8">
                      {project.links.live !== '#' && (
                        <a
                          href={project.links.live}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="w-full max-w-xs bg-cyan-500 hover:bg-cyan-600 text-white px-12 py-6 rounded-lg text-center text-xl font-semibold transition-all"
                          suppressHydrationWarning
                        >
                          View Live Demo →
                        </a>
                      )}
                      {project.links.github !== '#' && (
                        <a
                          href={project.links.github}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="w-full max-w-xs bg-slate-700 hover:bg-slate-600 text-white px-12 py-6 rounded-lg text-center text-xl font-semibold transition-all flex items-center justify-center gap-4"
                          suppressHydrationWarning
                        >
                          <Github size={24} />
                          GitHub
                        </a>
                      )}
                    </div>
                  </div>

                  {/* Content */}
                  <div className="flex-1 flex flex-col">
                    {/* Badge - More spacing */}
                    {project.badge && (
                      <motion.span
                        className="inline-flex items-center gap-2 bg-yellow-500/10 border border-yellow-500/30 text-yellow-400 px-4 py-2 rounded-full text-sm font-medium mb-6 w-fit"
                        initial={{ scale: 0 }}
                        animate={inView ? { scale: 1 } : {}}
                        transition={{ delay: index * 0.1 + 0.2, type: 'spring' }}
                      >
                        <Trophy className="w-4 h-4" />
                        {project.badge}
                      </motion.span>
                    )}

                    {/* Title - Bigger with more spacing */}
                    <motion.h3
                      className="text-2xl md:text-3xl font-bold text-white mb-5 group-hover:text-cyan-400 transition-colors leading-tight break-words"
                      initial={{ opacity: 0 }}
                      animate={inView ? { opacity: 1 } : {}}
                      transition={{ delay: index * 0.1 + 0.3 }}
                    >
                      {project.title}
                    </motion.h3>
                    <p className="text-slate-400 text-base md:text-lg mb-5">{project.date}</p>
                    <p className="text-slate-400 text-lg md:text-xl leading-relaxed mb-10 flex-1 break-words">{project.description}</p>

                    {/* Metrics Grid - More spacing */}
                    <div className="grid grid-cols-2 gap-5 mb-10">
                      {project.metrics.map((metric, metricIndex) => (
                        <motion.div
                          key={metricIndex}
                          className="bg-slate-950/50 border border-slate-800 rounded-lg p-5 text-center overflow-hidden container-content"
                          whileHover={{ scale: 1.05, borderColor: 'rgba(6, 182, 212, 0.5)' }}
                          initial={{ opacity: 0, scale: 0.8 }}
                          animate={inView ? { opacity: 1, scale: 1 } : {}}
                          transition={{ delay: index * 0.1 + metricIndex * 0.1 + 0.4 }}
                          style={{ transformOrigin: 'center' }}
                        >
                          <div className="text-cyan-400 font-bold text-xl md:text-2xl mb-2 break-words">{metric.value}{metric.suffix}</div>
                          <div className="text-slate-500 text-sm md:text-base break-words">{metric.label}</div>
                        </motion.div>
                      ))}
                    </div>

                    {/* Tech Stack - Larger pills with more spacing */}
                    <div className="flex flex-wrap gap-4 mb-8">
                      {project.tech.slice(0, 4).map((tech, techIndex) => (
                        <motion.span
                          key={tech}
                          className="bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 px-4 py-2 rounded-lg text-sm font-medium"
                          initial={{ opacity: 0, x: -10 }}
                          animate={inView ? { opacity: 1, x: 0 } : {}}
                          transition={{ delay: index * 0.1 + techIndex * 0.05 + 0.6 }}
                          whileHover={{ scale: 1.05, borderColor: 'rgba(6, 182, 212, 0.6)' }}
                        >
                          {tech}
                        </motion.span>
                      ))}
                      {project.tech.length > 4 && (
                        <motion.span
                          className="bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 px-4 py-2 rounded-lg text-sm font-medium"
                          initial={{ opacity: 0 }}
                          animate={inView ? { opacity: 1 } : {}}
                          transition={{ delay: index * 0.1 + 0.7 }}
                        >
                          +{project.tech.length - 4}
                        </motion.span>
                      )}
                    </div>

                    {/* Expandable Features */}
                    <AnimatePresence>
                      {expandedId === project.id && (
                        <motion.div
                          initial={{ opacity: 0, height: 0 }}
                          animate={{ opacity: 1, height: 'auto' }}
                          exit={{ opacity: 0, height: 0 }}
                          transition={{ duration: 0.3 }}
                          className="mb-4 space-y-3 overflow-hidden"
                        >
                          <h4 className="text-sm font-semibold text-slate-200">Key Features:</h4>
                          <ul className="space-y-2">
                            {project.features.map((feature, featureIndex) => (
                              <motion.li
                                key={featureIndex}
                                className="text-xs text-slate-400 flex items-start gap-2"
                                initial={{ opacity: 0, x: -10 }}
                                animate={{ opacity: 1, x: 0 }}
                                transition={{ delay: featureIndex * 0.05 }}
                              >
                                <span className="text-cyan-400 mt-1">•</span>
                                <span>{feature}</span>
                              </motion.li>
                            ))}
                          </ul>
                          <div className="flex flex-wrap gap-2 pt-2">
                            {project.tech.map((tech) => (
                              <span
                                key={tech}
                                className="px-2 py-1 bg-gradient-to-r from-cyan-500/10 to-blue-500/10 border border-cyan-500/30 text-cyan-300 rounded-full text-xs font-medium"
                              >
                                {tech}
                              </span>
                            ))}
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>

                    {/* Actions */}
                    <div className="flex items-center justify-between gap-4 pt-6 border-t border-slate-700/50 mt-auto">
                      <motion.button
                        onClick={() => setExpandedId(expandedId === project.id ? null : project.id)}
                        className="flex items-center gap-2 px-4 py-2 text-base text-cyan-400 hover:text-cyan-300 transition-colors font-medium rounded-lg hover:bg-cyan-500/10"
                        whileHover={{ x: 5 }}
                        whileTap={{ scale: 0.95 }}
                      >
                        {expandedId === project.id ? (
                          <>
                            <ChevronUp size={20} />
                            Less
                          </>
                        ) : (
                          <>
                            <ChevronDown size={20} />
                            More
                          </>
                        )}
                      </motion.button>
                      <div className="flex gap-2">
                        {project.links.live !== '#' && (
                          <motion.a
                            href={project.links.live}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="p-2 bg-slate-700/50 border border-slate-600 rounded-lg hover:border-cyan-500 hover:bg-cyan-500/10 transition-all"
                            title="Live Demo"
                            whileHover={{ scale: 1.1, rotate: 5 }}
                            whileTap={{ scale: 0.9 }}
                            suppressHydrationWarning
                          >
                            <ExternalLink size={16} className="text-cyan-400" />
                          </motion.a>
                        )}
                        {project.links.github !== '#' && (
                          <motion.a
                            href={project.links.github}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="p-2 bg-slate-700/50 border border-slate-600 rounded-lg hover:border-emerald-500 hover:bg-emerald-500/10 transition-all"
                            title="GitHub"
                            whileHover={{ scale: 1.1, rotate: -5 }}
                            whileTap={{ scale: 0.9 }}
                            suppressHydrationWarning
                          >
                            <Github size={16} className="text-emerald-400" />
                          </motion.a>
                        )}
                      </div>
                    </div>
                  </div>
                </motion.div>
              </motion.div>
            ))}
          </div>
        </motion.div>
      </div>
    </section>
  );
}
