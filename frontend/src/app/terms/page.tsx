import { LegalPage, Section } from "@/components/LegalPage";
import { LEGAL } from "@/lib/legal";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Terms of Service · nfinit",
  description: "The agreement between you and Nfinit.",
};

const { operator, location, contactEmail, governingLaw, courts, minimumAge, monthlyPrice } =
  LEGAL;
const mail = `mailto:${contactEmail}`;

export default function TermsPage() {
  return (
    <LegalPage
      title="Terms of Service"
      summary={
        <ul>
          <li>
            Nfinit turns text descriptions into 3D CAD parts with AI. You can look at
            the demo parts for free. Building, editing and exporting parts needs a
            subscription of {monthlyPrice} per month, plus applicable taxes.
          </li>
          <li>
            The subscription renews every month until you cancel. You can cancel at
            any time with the <strong>Billing</strong> button in the studio, and you
            keep access until the end of the month you paid for.
          </li>
          <li>You own the parts you design and the prompts and images you give us.</li>
          <li>
            <strong>
              AI-generated parts can be wrong. Check every dimension, fit and strength
              requirement before you make or use a part.
            </strong>{" "}
            Do not use a part where a failure can hurt someone unless a qualified
            person has checked it.
          </li>
          <li>We do not sell your data, and we do not use your designs to train AI models.</li>
        </ul>
      }
    >
      <Section id="agreement" title="1. This agreement">
        <p>
          These Terms of Service (the &ldquo;Terms&rdquo;) are a contract between you and{" "}
          {operator} (&ldquo;Nfinit&rdquo;, &ldquo;we&rdquo;, &ldquo;us&rdquo;). They apply
          when you use the Nfinit website, studio and related services (the
          &ldquo;Service&rdquo;). Our <Link href="/privacy">Privacy Policy</Link> tells you
          how we handle your personal data.
        </p>
        <p>
          When you sign in, subscribe or use the Service, you agree to these Terms. If you
          do not agree, do not use the Service.
        </p>
      </Section>

      <Section id="eligibility" title="2. Who can use Nfinit">
        <p>
          You must be at least {minimumAge} years old. If you are under 18, or under the age
          of majority where you live, a parent or legal guardian must agree to these Terms
          for you and must make any purchase.
        </p>
        <p>
          If you use the Service for a company or other organization, you confirm that you
          can accept these Terms for it, and &ldquo;you&rdquo; includes that organization.
        </p>
      </Section>

      <Section id="account" title="3. Your account">
        <p>
          You sign in with your Google account. You are responsible for all activity on
          your Nfinit account. Keep your Google account secure, and tell us at{" "}
          <a href={mail}>{contactEmail}</a> if you think someone else has used your account.
          Do not share your account with other people.
        </p>
      </Section>

      <Section id="service" title="4. The Service">
        <p>
          Nfinit uses AI models to turn your descriptions, images and face selections into
          build123d CAD code. It runs that code to build a 3D part that you can view, change
          and export as STL or STEP files.
        </p>
        <ul>
          <li>
            <strong>Free:</strong> you can view the demo parts and replay how they were
            built.
          </li>
          <li>
            <strong>Subscription:</strong> you can generate and edit parts, select faces to
            change, use the code editor and export files.
          </li>
        </ul>
        <p>
          We work to keep the Service available and correct, but we can change, add or
          remove features. If we remove a main feature that you pay for, we will tell you
          first, and you can cancel.
        </p>
      </Section>

      <Section id="billing" title="5. Subscription, renewal and cancellation">
        <ul>
          <li>
            <strong>Price:</strong> {monthlyPrice} per month, charged in US dollars, plus
            applicable taxes such as GST/HST, sales tax or VAT. Checkout calculates the
            tax from your billing address and shows the total before you pay. Your bank
            can charge a fee to convert the currency.
          </li>
          <li>
            <strong>Automatic renewal:</strong> your subscription renews automatically
            every month, and we charge your payment method at the start of each month,
            until you cancel.
          </li>
          <li>
            <strong>How to cancel:</strong> select <strong>Billing</strong> (the card
            icon) in the studio toolbar, then select <strong>Cancel subscription</strong>{" "}
            on the page that opens. You can also email us at{" "}
            <a href={mail}>{contactEmail}</a>. Cancellation stops the next renewal. You
            keep access until the end of the month you already paid for.
          </li>
          <li>
            <strong>Refunds:</strong> payments are not refundable for a partly used month,
            except where the law requires a refund. If we charged you by mistake, or the
            Service did not work for a large part of a month, email us and we will make it
            right.
          </li>
          <li>
            <strong>Price changes:</strong> we will tell you at least 30 days before a new
            price applies to you. If you do not agree, you can cancel before it starts.
          </li>
          <li>
            <strong>Failed payments:</strong> if a payment fails, our payment provider tries
            again. If payment still fails, your subscription ends and the paid features
            stop.
          </li>
          <li>
            <strong>Payments:</strong> Stripe processes all payments. We never see or keep
            your full card number.
          </li>
          <li>
            <strong>Your copy:</strong> Stripe emails you a receipt for each payment. These
            Terms are always available at <Link href="/terms">nfinit.dev/terms</Link>, and
            we will email you a copy if you ask.
          </li>
        </ul>
      </Section>

      <Section id="your-content" title="6. Your content and your designs">
        <p>
          &ldquo;Your Content&rdquo; means the prompts, images and other material you give
          us, and the code, plans and 3D parts that the Service makes for you.{" "}
          <strong>You own Your Content.</strong> We do not claim ownership of it.
        </p>
        <p>
          You give us permission to store, copy, process and send Your Content only as
          needed to run the Service for you. This includes sending it to the service
          providers listed in our <Link href="/privacy">Privacy Policy</Link>, such as the
          AI model providers. This permission ends when you delete Your Content or your
          account, except for copies in backups until they expire and copies the law
          requires us to keep.
        </p>
        <p>
          We do not sell Your Content, and we do not use it to train AI models. If we ever
          want to use it to improve the Service in a new way, we will ask you first, and
          you can say no.
        </p>
        <p>
          You confirm that you have the right to give us Your Content. For example, do not
          upload images or drawings that you do not have permission to use.
        </p>
      </Section>

      <Section id="ai-output" title="7. AI-generated output">
        <p>
          AI output can be wrong, incomplete or different from what you asked for. The
          same or a similar output can be made for other users. Before you use a design,
          you are responsible for checking that:
        </p>
        <ul>
          <li>it is correct for your purpose; and</li>
          <li>
            it does not copy another person&rsquo;s protected design, patent, trademark or
            other rights.
          </li>
        </ul>
      </Section>

      <Section id="safety" title="8. Engineering and safety">
        <p className="legal-callout">
          <strong>
            Nfinit is a design tool. It does not check that a part is strong enough, safe,
            or suitable for any use. Dimensions, tolerances, wall thickness, materials and
            load capacity are not verified by an engineer.
          </strong>
        </p>
        <p>
          Before you make, sell or use a part, check it yourself. Do not use a part where a
          failure can cause injury, death or major damage, unless a qualified professional
          has checked and tested it. Examples are parts that carry people or heavy loads,
          parts of vehicles, aircraft, drones flown near people, medical devices, pressure
          systems and safety equipment.
        </p>
        <p>
          You are responsible for how you make and use parts, and for following the laws
          that apply to them.
        </p>
      </Section>

      <Section id="acceptable-use" title="9. Acceptable use">
        <p>Do not use the Service to:</p>
        <ul>
          <li>break any law, or help another person break a law;</li>
          <li>
            design firearms, firearm parts or accessories, explosive devices or other
            weapons;
          </li>
          <li>copy or infringe another person&rsquo;s intellectual property;</li>
          <li>
            attack, overload or interfere with the Service, or try to get around its
            sandbox, security, usage limits or paywall;
          </li>
          <li>
            copy, scrape, resell or give other people access to the Service, or use it to
            build a competing product;
          </li>
          <li>
            reverse engineer the Service, except where the law allows this even when a
            contract says no; or
          </li>
          <li>harass, deceive or harm other people.</li>
        </ul>
        <p>
          We can remove content or suspend accounts that break this section (see
          section&nbsp;12).
        </p>
      </Section>

      <Section id="our-rights" title="10. Our software and open-source software">
        <p>
          We own the Nfinit software, name, logo and website, except for Your Content and
          third-party software. These Terms give you a personal, non-transferable right to
          use the Service while your account is active. They do not give you any other
          rights in our software or brand.
        </p>
        <p>
          The Service uses open-source software, including build123d (Apache License 2.0)
          and Open CASCADE Technology (GNU LGPL 2.1 with the Open CASCADE exception). Their
          licenses apply to that software, and these Terms do not limit your rights under
          them.
        </p>
      </Section>

      <Section id="feedback" title="11. Feedback">
        <p>
          If you send us ideas or suggestions, we can use them without paying you or
          naming you. This does not give us any rights in Your Content.
        </p>
      </Section>

      <Section id="termination" title="12. Ending this agreement">
        <p>
          You can stop using the Service at any time. To delete your account and all your
          data, select <strong>Delete account</strong> on the{" "}
          <Link href="/account">Account page</Link>. This also cancels your subscription
          at once, without a refund for the rest of the month. You can also email us at{" "}
          <a href={mail}>{contactEmail}</a>.
        </p>
        <p>
          We can suspend or close your account if you seriously or repeatedly break these
          Terms, if the law requires it, or if your use creates a risk to the Service or
          other people. When possible, we will tell you first and give you time to export
          your designs. If we close the Service or your account for a reason that is not
          your fault, we will refund the unused part of your current month.
        </p>
        <p>
          Sections 6 to 8, 10, 11 and 13 to 17 stay in effect after this agreement ends.
        </p>
      </Section>

      <Section id="disclaimers" title="13. Disclaimers">
        <p>
          We provide the Service &ldquo;as is&rdquo; and &ldquo;as available&rdquo;. To the
          extent the law allows, we make no warranties of any kind, express or implied,
          including warranties of merchantability, fitness for a particular purpose,
          non-infringement, accuracy, or that the Service will be uninterrupted or free of
          errors.
        </p>
        <p>
          Some places do not allow these disclaimers. In those places, they apply only as
          far as the law allows, and you keep the rights that the law gives you. If you are
          a consumer, nothing in these Terms limits the rights you have under consumer
          protection law, including Ontario&rsquo;s consumer protection legislation.
        </p>
      </Section>

      <Section id="liability" title="14. Limitation of liability">
        <p>To the extent the law allows:</p>
        <ul>
          <li>
            we are not responsible for indirect, incidental, special, consequential or
            punitive damages, or for lost profits, revenue, data or business, even if we
            knew they were possible; and
          </li>
          <li>
            our total responsibility for all claims about the Service is limited to the
            greater of (a) the amount you paid us in the 12 months before the event that
            caused the claim, and (b) US$50.
          </li>
        </ul>
        <p>
          This section does not limit responsibility that the law does not allow us to
          limit, for example for fraud, or for death or personal injury caused by our
          negligence.
        </p>
      </Section>

      <Section id="indemnity" title="15. Your responsibility to us">
        <p>
          If another person makes a claim against us because you broke these Terms or the
          law, or because of a part you made, sold or used, you agree to pay the reasonable
          costs and damages that result, to the extent the law allows. This does not apply
          if we caused the problem.
        </p>
      </Section>

      <Section id="changes" title="16. Changes to these Terms">
        <p>
          We can change these Terms. If a change is important, we will tell you by email or
          in the studio at least 14 days before it applies, unless the law or a security
          problem requires a faster change. The new Terms apply from the date shown at the
          top of this page. If you do not agree, stop using the Service and cancel your
          subscription.
        </p>
      </Section>

      <Section id="law" title="17. Governing law and disputes">
        <p>
          Please contact us first at <a href={mail}>{contactEmail}</a>. Most problems can be
          solved quickly this way.
        </p>
        <p>
          These Terms are governed by the laws of {governingLaw}, without regard to
          conflict-of-law rules. Any dispute that we cannot solve together goes to the
          courts in {courts}, and both of us agree to those courts. Either of us can also
          use a small-claims court where it has jurisdiction.
        </p>
        <p>
          If you are a consumer, and the law where you live (for example in Quebec, the
          European Union or the United Kingdom) gives you mandatory protection or the right
          to go to your local courts, you keep that protection and that right.
        </p>
      </Section>

      <Section id="general" title="18. General">
        <p>
          These Terms and the Privacy Policy are the full agreement between you and us
          about the Service. If a court finds part of these Terms invalid, the rest stays in
          effect. If we do not enforce a part of these Terms, we can still enforce it later.
          You cannot transfer these Terms to another person without our permission. We can
          transfer them to a company that takes over the Service, and we will tell you if
          this happens.
        </p>
      </Section>

      <Section id="contact" title="19. Contact">
        <p>
          {operator}
          <br />
          {location}
          <br />
          Email: <a href={mail}>{contactEmail}</a>
        </p>
      </Section>
    </LegalPage>
  );
}
