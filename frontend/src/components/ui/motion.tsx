import React from 'react';
import { motion, type HTMLMotionProps } from 'framer-motion';

/** Fade + rise entrance. `delay` staggers items in a list. */
export const FadeIn: React.FC<
  HTMLMotionProps<'div'> & { delay?: number; y?: number }
> = ({ delay = 0, y = 12, children, ...props }) => (
  <motion.div
    initial={{ opacity: 0, y }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ duration: 0.45, delay, ease: [0.22, 1, 0.36, 1] }}
    {...props}
  >
    {children}
  </motion.div>
);

/** Container that staggers its FadeIn children. */
export const Stagger: React.FC<HTMLMotionProps<'div'> & { gap?: number }> = ({
  gap = 0.06,
  children,
  ...props
}) => (
  <motion.div
    initial="hidden"
    animate="show"
    variants={{
      hidden: {},
      show: { transition: { staggerChildren: gap } },
    }}
    {...props}
  >
    {children}
  </motion.div>
);

export const StaggerItem: React.FC<HTMLMotionProps<'div'>> = ({ children, ...props }) => (
  <motion.div
    variants={{
      hidden: { opacity: 0, y: 14 },
      show: { opacity: 1, y: 0, transition: { duration: 0.45, ease: [0.22, 1, 0.36, 1] } },
    }}
    {...props}
  >
    {children}
  </motion.div>
);
