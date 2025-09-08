from PIL import Image
import os
import logging
from models import SlipVerification, db
from datetime import datetime

logger = logging.getLogger(__name__)

class SlipVerifier:
    def __init__(self):
        pass
    
    def verify_slip(self, image_path, transaction_id=None):
        """Main slip verification function - simplified version"""
        try:
            # Load image
            image = Image.open(image_path)
            if image is None:
                return self._create_result("error", 0.0, {"error": "Cannot load image"})
            
            # Basic checks
            checks = {
                "file_format": self._check_file_format(image),
                "image_size": self._check_image_size(image),
                "basic_quality": self._check_basic_quality(image)
            }
            
            # Calculate overall score
            score = sum(checks.values()) / len(checks)
            
            if score >= 0.7:
                result_type = "genuine"
            elif score >= 0.4:
                result_type = "suspicious"
            else:
                result_type = "fake"
            
            result = self._create_result(result_type, score, checks)
            
            # Store verification result
            if transaction_id:
                self.store_verification_result(transaction_id, image_path, result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error verifying slip: {str(e)}")
            return self._create_result("error", 0.0, {"error": str(e)})
    
    def _check_file_format(self, image):
        """Check if file format is appropriate"""
        valid_formats = ['JPEG', 'PNG', 'JPG']
        if image.format in valid_formats:
            return 0.8
        else:
            return 0.2
    
    def _check_image_size(self, image):
        """Check image dimensions"""
        width, height = image.size
        pixel_count = width * height
        
        if pixel_count > 300000:  # Good resolution
            return 0.9
        elif pixel_count > 100000:
            return 0.6
        else:
            return 0.3
    
    def _check_basic_quality(self, image):
        """Basic quality checks"""
        try:
            # Check if image has reasonable aspect ratio
            width, height = image.size
            aspect_ratio = width / height
            
            if 0.3 <= aspect_ratio <= 3.0:  # Reasonable aspect ratio
                return 0.7
            else:
                return 0.3
        except:
            return 0.5
    
    def _create_result(self, result_type, score, details):
        """Create standardized verification result"""
        return {
            "result": result_type,
            "score": score,
            "details": details,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    def store_verification_result(self, transaction_id, image_path, verification_result):
        """Store verification result in database"""
        try:
            verification = SlipVerification(
                transaction_id=transaction_id,
                slip_image_path=image_path,
                verification_result=verification_result["result"],
                verification_score=verification_result["score"],
                verification_details=verification_result["details"],
                verified_by="system"
            )
            
            db.session.add(verification)
            db.session.commit()
            
            logger.info(f"Stored verification result for transaction {transaction_id}")
            
        except Exception as e:
            logger.error(f"Error storing verification result: {str(e)}")
            db.session.rollback()

# Global instance
slip_verifier = SlipVerifier()