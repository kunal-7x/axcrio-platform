import Icon from "@/components/Icon";
import Modal from "@/components/Modal";
import Button from "@/components/Button";

type ConfirmDeleteModalProps = {
    open: boolean;
    onClose: () => void;
    onConfirm: () => void;
    title?: string;
    message?: React.ReactNode;
    confirmLabel?: string;
    cancelLabel?: string;
    busy?: boolean;
    busyLabel?: string;
};

/**
 * Reusable Core_2 confirm-delete CARD/modal — replaces native window.confirm()
 * across leads, CRM, calls, bookings, campaigns, webhooks and the
 * Do-Not-Call list. Matches the existing dashboard Modal/Button style.
 */
const ConfirmDeleteModal = ({
    open,
    onClose,
    onConfirm,
    title = "Are you sure?",
    message = "This action cannot be undone.",
    confirmLabel = "Delete",
    cancelLabel = "Cancel",
    busy = false,
    busyLabel = "Deleting…",
}: ConfirmDeleteModalProps) => {
    return (
        <Modal
            open={open}
            onClose={() => {
                if (!busy) onClose();
            }}
        >
            <div className="flex justify-center items-center size-16 mb-8 bg-primary-03/15 rounded-full">
                <Icon name="trash" className="size-6 fill-primary-03" />
            </div>
            <div className="mb-4 text-h4 max-md:text-h5">{title}</div>
            <div className="mb-8 text-body-2 font-medium text-t-tertiary">
                {message}
            </div>
            <div className="flex justify-end gap-3 mt-8">
                <Button
                    className="flex-1"
                    isStroke
                    onClick={onClose}
                    disabled={busy}
                >
                    {cancelLabel}
                </Button>
                <Button
                    className="flex-1"
                    isBlack
                    onClick={onConfirm}
                    disabled={busy}
                >
                    {busy ? busyLabel : confirmLabel}
                </Button>
            </div>
        </Modal>
    );
};

export default ConfirmDeleteModal;
