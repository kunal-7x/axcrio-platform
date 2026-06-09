import Link from "next/link";
import Image from "@/components/Image";

type LogoProps = {
    className?: string;
};

const Logo = ({ className }: LogoProps) => {
    return (
        <Link
            className={`block w-fit ${className || ""}`}
            href="/"
        >
            {/* Light-mode logo (hidden in dark mode) */}
            <Image
                className="h-10 w-auto block dark:hidden"
                src="/images/logo-light.png"
                alt="Famit"
                width={40}
                height={40}
                priority
            />
            {/* Dark-mode logo (hidden in light mode) */}
            <Image
                className="h-10 w-auto hidden dark:block"
                src="/images/logo-dark.png"
                alt="Famit"
                width={40}
                height={40}
                priority
            />
        </Link>
    );
};

export default Logo;
