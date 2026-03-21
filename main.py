#!/usr/bin/env python3
"""open-PROX - Proximity Awareness System display mock."""

from display.renderer import Renderer
from tools.synthetic_targets import SyntheticTargetGenerator


def main():
    renderer = Renderer()
    generator = SyntheticTargetGenerator()

    running = True
    while running:
        running = renderer.handle_events()
        contacts = generator.generate()
        renderer.render(contacts)

    renderer.shutdown()


if __name__ == "__main__":
    main()
