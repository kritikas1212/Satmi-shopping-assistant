'use client';

import { motion } from 'framer-motion';
import { useInView } from 'react-intersection-observer';
import { Clock, Calendar, ArrowRight } from 'lucide-react';

const blogPosts = [
  {
    title: 'How I Achieved 95% Performance Boost in Shopify Themes',
    excerpt: 'Strategic optimization techniques that reduced page load time by 40% and improved user experience significantly...',
    date: 'Coming Soon',
    readTime: '8 min',
    tags: ['Shopify', 'Performance', 'Optimization'],
    status: 'Draft',
  },
  {
    title: 'Building a 99% Accurate Brain Tumor Classifier with Transfer Learning',
    excerpt: 'Deep dive into transfer learning optimization and medical imaging techniques that achieved exceptional accuracy...',
    date: 'Coming Soon',
    readTime: '12 min',
    tags: ['Machine Learning', 'TensorFlow', 'Healthcare'],
    status: 'Draft',
  },
  {
    title: 'My Journey: Dual Degrees at IIT Madras and Full-Stack Development',
    excerpt: 'Balancing B.Tech and B.S. while working as a software developer - lessons learned and tips for success...',
    date: 'Coming Soon',
    readTime: '6 min',
    tags: ['Career', 'Education', 'Tips'],
    status: 'Draft',
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
  hidden: { opacity: 0, y: 30 },
  visible: {
    opacity: 1,
    y: 0,
  },
};

export default function Blog() {
  const { ref, inView } = useInView({ threshold: 0.1, triggerOnce: true });

  return (
    <section id="blog" className="relative py-20 md:py-32 bg-slate-900">
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
              <span className="text-slate-300">Blog & </span>
              <span className="text-cyan-400">Articles</span>
            </h2>
            <motion.div
              className="w-32 h-1 bg-gradient-to-r from-cyan-500 to-blue-500 mx-auto rounded-full"
              initial={{ width: 0 }}
              animate={inView ? { width: 128 } : {}}
              transition={{ delay: 0.3, duration: 0.8 }}
            />
          </motion.div>

          {/* Blog Posts Grid - More Spacious */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-12">
            {blogPosts.map((post, index) => (
              <motion.article
                key={index}
                variants={itemVariants}
                className="group relative bg-gradient-to-br from-slate-800/80 to-slate-900/80 rounded-xl overflow-hidden border border-slate-700/50 hover:border-cyan-500/50 transition-all duration-500 hover:shadow-2xl hover:shadow-cyan-500/20 container-content"
                whileHover={{ scale: 1.03, y: -8 }}
                style={{ transformOrigin: 'center' }}
              >
                {/* Image placeholder with gradient */}
                <div className="h-56 bg-gradient-to-br from-cyan-500/20 via-blue-500/20 to-purple-500/20 flex items-center justify-center relative overflow-hidden">
                  <div className="text-8xl">📝</div>

                  {/* Draft badge */}
                  <span className="absolute top-6 left-6 bg-yellow-500/20 border border-yellow-500/50 text-yellow-400 px-4 py-2 rounded-full text-sm font-semibold backdrop-blur-sm">
                    {post.status}
                  </span>
                </div>

                <div className="p-10 md:p-12">
                  <h3 className="text-2xl font-bold text-white mb-4 group-hover:text-cyan-400 transition-colors line-clamp-2 leading-tight">
                    {post.title}
                  </h3>

                  {/* Excerpt */}
                  <p className="text-slate-400 mb-6 line-clamp-3 text-base leading-relaxed">{post.excerpt}</p>

                  {/* Meta Info */}
                  <div className="flex items-center gap-6 text-base text-slate-500 mb-6">
                    <div className="flex items-center gap-2">
                      <Calendar size={16} />
                      {post.date}
                    </div>
                    <div className="flex items-center gap-2">
                      <Clock size={16} />
                      {post.readTime}
                    </div>
                  </div>

                  {/* Tags */}
                  <div className="flex flex-wrap gap-3 mb-6">
                    {post.tags.map((tag) => (
                      <span
                        key={tag}
                        className="px-3 py-1.5 bg-slate-700/50 text-slate-300 rounded-lg text-sm border border-slate-600"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>

                  {/* Read More */}
                  <button className="flex items-center gap-3 px-6 py-3 text-cyan-400 hover:text-cyan-300 hover:bg-cyan-500/10 transition-all text-lg font-medium group/btn rounded-lg">
                    Read More
                    <ArrowRight size={20} className="group-hover/btn:translate-x-1 transition-transform" />
                  </button>
                </div>
              </motion.article>
            ))}
          </div>
        </motion.div>
      </div>
    </section>
  );
}
