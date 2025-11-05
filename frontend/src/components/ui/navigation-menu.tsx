"use client";

import * as React from "react";
import * as NavigationPrimitive from "@radix-ui/react-navigation-menu";
import { cn } from "@/lib/utils";

export const NavigationMenu = React.forwardRef<
  React.ElementRef<typeof NavigationPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof NavigationPrimitive.Root>
>(({ className, ...props }, ref) => (
  <NavigationPrimitive.Root
    ref={ref}
    className={cn("relative z-10 flex w-full justify-center", className)}
    {...props}
  />
));
NavigationMenu.displayName = "NavigationMenu";

export const NavigationMenuList = React.forwardRef<
  React.ElementRef<typeof NavigationPrimitive.List>,
  React.ComponentPropsWithoutRef<typeof NavigationPrimitive.List>
>(({ className, ...props }, ref) => (
  <NavigationPrimitive.List
    ref={ref}
    className={cn(
      "flex items-center gap-2 rounded-2xl bg-gray-900/60 p-1 ring-1 ring-gray-800/70",
      className
    )}
    {...props}
  />
));
NavigationMenuList.displayName = "NavigationMenuList";

export const NavigationMenuItem = NavigationPrimitive.Item;

export const NavigationMenuTrigger = React.forwardRef<
  React.ElementRef<typeof NavigationPrimitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof NavigationPrimitive.Trigger>
>(({ className, ...props }, ref) => (
  <NavigationPrimitive.Trigger
    ref={ref}
    className={cn(
      "px-4 py-2 text-sm rounded-xl text-gray-200 hover:text-white",
      "data-[state=open]:bg-gray-800/70",
      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/60",
      className
    )}
    {...props}
  />
));
NavigationMenuTrigger.displayName = "NavigationMenuTrigger";

export const NavigationMenuLink = React.forwardRef<
  React.ElementRef<typeof NavigationPrimitive.Link>,
  React.ComponentPropsWithoutRef<typeof NavigationPrimitive.Link>
>(({ className, ...props }, ref) => (
  <NavigationPrimitive.Link
    ref={ref}
    className={cn(
      "px-4 py-2 text-sm rounded-xl text-gray-300 hover:text-white hover:bg-gray-800/60 focus-visible:outline-none",
      className
    )}
    {...props}
  />
));
NavigationMenuLink.displayName = "NavigationMenuLink";
