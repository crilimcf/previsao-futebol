"use client";

import * as React from "react";
import * as AccordionPrimitive from "@radix-ui/react-accordion";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

export const Accordion = AccordionPrimitive.Root;

export const AccordionItem = React.forwardRef<
  React.ElementRef<typeof AccordionPrimitive.Item>,
  React.ComponentPropsWithoutRef<typeof AccordionPrimitive.Item> & { inset?: boolean }
>(({ className, ...props }, ref) => (
  <AccordionPrimitive.Item
    ref={ref}
    className={cn(
      "border border-gray-800/70 rounded-xl bg-gray-900/60 backdrop-blur-sm overflow-hidden",
      className
    )}
    {...props}
  />
));
AccordionItem.displayName = "AccordionItem";

export const AccordionTrigger = React.forwardRef<
  React.ElementRef<typeof AccordionPrimitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof AccordionPrimitive.Trigger>
>(({ className, children, ...props }, ref) => (
  <AccordionPrimitive.Header className="flex">
    <AccordionPrimitive.Trigger
      ref={ref}
      className={cn(
        "group flex flex-1 items-center justify-between px-4 py-3 text-left text-sm font-medium",
        "text-gray-200 hover:text-white transition-colors",
        "bg-gradient-to-r from-gray-900/60 to-gray-900/30",
        "data-[state=open]:from-gray-900/30 data-[state=open]:to-gray-900/60",
        className
      )}
      {...props}
    >
      <span>{children}</span>
      <ChevronDown
        className="h-4 w-4 shrink-0 transition-transform duration-200 text-gray-400 group-data-[state=open]:rotate-180"
        aria-hidden="true"
      />
    </AccordionPrimitive.Trigger>
  </AccordionPrimitive.Header>
));
AccordionTrigger.displayName = AccordionPrimitive.Trigger.displayName;

export const AccordionContent = React.forwardRef<
  React.ElementRef<typeof AccordionPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof AccordionPrimitive.Content>
>(({ className, children, ...props }, ref) => (
  <AccordionPrimitive.Content
    ref={ref}
    className={cn(
      "data-[state=closed]:animate-accordion-up data-[state=open]:animate-accordion-down",
      "text-sm text-gray-200"
    )}
    {...props}
  >
    <div className={cn("px-4 pb-4 pt-0 border-t border-gray-800/70", className)}>{children}</div>
  </AccordionPrimitive.Content>
));
AccordionContent.displayName = AccordionPrimitive.Content.displayName;
