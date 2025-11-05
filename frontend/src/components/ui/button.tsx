"use client";

import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  [
    "inline-flex items-center justify-center gap-2 rounded-xl",
    "font-medium transition-colors focus-visible:outline-none",
    "disabled:pointer-events-none disabled:opacity-50",
    "ring-1 ring-inset",
  ].join(" "),
  {
    variants: {
      variant: {
        primary:
          "bg-green-500/90 hover:bg-green-500 text-black ring-green-400/20",
        secondary:
          "bg-gray-800 hover:bg-gray-700 text-gray-100 ring-gray-700",
        ghost:
          "bg-transparent hover:bg-gray-800/60 text-gray-100 ring-transparent",
        outline:
          "bg-transparent text-gray-100 ring-gray-700 hover:bg-gray-900/50",
        neon:
          "bg-gray-900/40 text-gray-100 ring-emerald-400/40 shadow-[0_0_25px_-10px_rgba(16,185,129,.7)] hover:shadow-[0_0_35px_-8px_rgba(16,185,129,.9)]",
      },
      size: {
        sm: "h-8 px-3 text-xs",
        md: "h-10 px-4 text-sm",
        lg: "h-12 px-5 text-sm",
        icon: "h-10 w-10 p-0",
      },
    },
    defaultVariants: {
      variant: "secondary",
      size: "md",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button
      ref={ref}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  )
);
Button.displayName = "Button";
