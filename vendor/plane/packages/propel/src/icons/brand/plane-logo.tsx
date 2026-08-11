/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import * as React from "react";

import type { ISvgIcons } from "../type";

export function PlaneLogo({ width = "32", height = "32", className, color = "currentColor" }: ISvgIcons) {
  return (
    <svg
      width={width}
      height={height}
      viewBox="0 0 64 64"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      <path
        d="M8,12 L36,12 L44,20 L44,27 L32,36 L15,36 L15,44 L23,52 L44,52"
        fill="none"
        stroke={color}
        stroke-width="11"
        stroke-linejoin="miter"
        stroke-linecap="butt"
      />
    </svg>
  );
}
